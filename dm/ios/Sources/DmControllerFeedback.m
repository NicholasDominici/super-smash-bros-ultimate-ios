// Independent authored rumble/motion, plus each game's verified controller accents.
#import <UIKit/UIKit.h>
#import <CoreHaptics/CoreHaptics.h>
#import "DmControllerFeedback.h"
#include <stdatomic.h>
#include <math.h>
#include "dm.h"
#include "dm_feedback.h"
#include "dm_input.h"
#include "dm_feedback_policy.h"
#include "odyssey_feedback.h"
#include "smash_feedback.h"

static dispatch_queue_t queue, diagnostics, triggerQueue;
static dispatch_source_t timer;
static char queueKey;
@interface DmControllerFeedbackState : NSObject {
@public
    unsigned player;
    GCController *selected;
    BOOL stereo;
    unsigned caps;
    _Atomic uint64_t motionEpoch, motionCount;
    CHHapticEngine *engines[2];
    id<CHHapticPatternPlayer> players[2];
    uint64_t generation[2], retry[2], started[2], lastActive[2];
    uint64_t hapticStarts[2], updates[2], nonzero[2], lastSequence[2];
    float sentIntensity[2], sentSharpness[2], travel[2];
    BOOL triggerOn[2];
    unsigned smashTriggerMode[2];
    uint64_t smashTriggerAt[2], smashImpactSequence[2];
    uint64_t triggerCommands[2], triggerEventSequence[2], jumpAt, jumpSequence, jumps, backflips, wallJumps, sideFlips, reportAt;
    dm_odyssey_feedback_kind jumpKind;
    // Only triggerQueue touches these tokens and the physical trigger modes. Its
    // deadline is independent of CoreHaptics engine creation and parameter calls.
    uint64_t triggerLease[2];
    uint64_t triggerReplyToken[2];
    _Atomic uint64_t triggerActiveReplies[2];
    _Atomic uint64_t triggerStartedNs[2], triggerStoppedNs[2], triggerPulseSequence[2];
    _Atomic int triggerReplyMode[2], triggerReplyStatus[2];
    _Atomic float triggerReplyArm[2];
}
@end
@implementation DmControllerFeedbackState
@end
static DmControllerFeedbackState *contexts[DM_FEEDBACK_MAX_PLAYERS];
static CHHapticPattern *pattern;
static BOOL active;
static uint64_t frameCount, frameAt;
static BOOL odyssey_effects(void) { return DM_GAME_PROGRAM_ID == 0x0100000000010000ull; }
static BOOL smash_effects(void) { return DM_GAME_PROGRAM_ID == 0x01006a800016e000ull; }
static const float smash_guard_resistance = .12f, smash_guard_impact = .34f;
static const uint64_t smash_guard_pulse_ns = 55000000;

static void on_queue(dispatch_block_t work) {
    if (dispatch_get_specific(&queueKey)) work(); else dispatch_sync(queue, work);
}
static GCDualSenseGamepad *dualsense(DmControllerFeedbackState *ctx) {
    GCExtendedGamepad *g = ctx->selected.extendedGamepad;
    return [g isKindOfClass:GCDualSenseGamepad.class] ? (GCDualSenseGamepad *)g : nil;
}
static void triggers_off(DmControllerFeedbackState *ctx) {
    GCDualSenseGamepad *g = dualsense(ctx);
    dispatch_sync(triggerQueue, ^{
        ctx->triggerLease[0]++; ctx->triggerLease[1]++;
        [g.leftTrigger setModeOff]; [g.rightTrigger setModeOff];
        atomic_store(&ctx->triggerStoppedNs[0], now_ns()); atomic_store(&ctx->triggerStoppedNs[1], now_ns());
    });
    ctx->triggerOn[0] = ctx->triggerOn[1] = NO;
    ctx->smashTriggerMode[0] = ctx->smashTriggerMode[1] = 0;
    ctx->smashTriggerAt[0] = ctx->smashTriggerAt[1] = 0;
    ctx->smashImpactSequence[0] = ctx->smashImpactSequence[1] = 0;
}
static void release_engine(DmControllerFeedbackState *ctx, int side) {
    ctx->generation[side]++;
    [ctx->players[side] stopAtTime:CHHapticTimeImmediate error:nil]; ctx->players[side] = nil;
    CHHapticEngine *e = ctx->engines[side]; ctx->engines[side] = nil;
    e.resetHandler = ^{}; e.stoppedHandler = ^(CHHapticEngineStoppedReason reason) { (void)reason; };
    [e stopWithCompletionHandler:nil];
    ctx->started[side] = ctx->lastActive[side] = 0;
    ctx->sentIntensity[side] = ctx->sentSharpness[side] = -1;
}
static void quiet(DmControllerFeedbackState *ctx) {
    triggers_off(ctx);
    for (int side = 0; side < 2; side++) release_engine(ctx, side);
    ctx->jumpAt = ctx->jumpSequence = 0; ctx->jumpKind = 0;
    ctx->triggerEventSequence[0] = ctx->triggerEventSequence[1] = 0;
    ctx->travel[0] = ctx->travel[1] = 0;
}
static void engine_failed(DmControllerFeedbackState *ctx, int side, NSString *operation, NSError *error) {
    LOG("controller-feedback: %s %s failed: %s", side ? "right" : "left", operation.UTF8String,
        error.localizedDescription.UTF8String ?: "unavailable");
    release_engine(ctx, side); ctx->retry[side] = now_ns() + 2000000000ull;
}
static BOOL ensure_engine(DmControllerFeedbackState *ctx, int side, uint64_t now) {
    if (ctx->engines[side]) return YES;
    if (!ctx->selected.haptics || now < ctx->retry[side]) return NO;
    NSError *error = nil;
    if (!pattern) {
        CHHapticEvent *event = [[CHHapticEvent alloc] initWithEventType:CHHapticEventTypeHapticContinuous
            parameters:@[[[CHHapticEventParameter alloc] initWithParameterID:CHHapticEventParameterIDHapticIntensity value:1],
                         [[CHHapticEventParameter alloc] initWithParameterID:CHHapticEventParameterIDHapticSharpness value:0.5f]]
            relativeTime:0 duration:0.20];
        pattern = [[CHHapticPattern alloc] initWithEvents:@[event] parameters:@[] error:&error];
        if (!pattern) { engine_failed(ctx, side, @"pattern", error); return NO; }
    }
    NSSet *localities = ctx->selected.haptics.supportedLocalities;
    GCHapticsLocality locality = ctx->stereo ? (side ? GCHapticsLocalityRightHandle : GCHapticsLocalityLeftHandle) :
        ([localities containsObject:GCHapticsLocalityDefault] ? GCHapticsLocalityDefault : localities.anyObject);
    if (!locality) return NO;
    CHHapticEngine *e = [ctx->selected.haptics createEngineWithLocality:locality];
    if (!e) { engine_failed(ctx, side, @"engine creation", nil); return NO; }
    e.playsHapticsOnly = YES;
    __weak CHHapticEngine *weakEngine = e;
    __weak DmControllerFeedbackState *weakContext = ctx;
    uint64_t token = ++ctx->generation[side];
    void (^lost)(void) = ^{
        CHHapticEngine *lostEngine = weakEngine;
        DmControllerFeedbackState *ctx = weakContext;
        if (!ctx) return;
        dispatch_async(queue, ^{
            if (ctx->generation[side] == token && ctx->engines[side] == lostEngine) {
                release_engine(ctx, side); ctx->retry[side] = now_ns() + 2000000000ull;
            }
        });
    };
    e.resetHandler = lost;
    e.stoppedHandler = ^(CHHapticEngineStoppedReason reason) { (void)reason; lost(); };
    if (![e startAndReturnError:&error]) { engine_failed(ctx, side, @"engine start", error); return NO; }
    ctx->engines[side] = e;
    LOG("controller-feedback: %s engine ready (%s)", side ? "right" : "left", locality.UTF8String);
    return YES;
}
static BOOL parameters(DmControllerFeedbackState *ctx, id<CHHapticPatternPlayer> player, int side, dm_handle_effect value) {
    NSError *error = nil;
    NSArray *p = @[
        [[CHHapticDynamicParameter alloc] initWithParameterID:CHHapticDynamicParameterIDHapticIntensityControl value:value.intensity relativeTime:0],
        [[CHHapticDynamicParameter alloc] initWithParameterID:CHHapticDynamicParameterIDHapticSharpnessControl value:value.sharpness - 0.5f relativeTime:0]];
    if (![player sendParameters:p atTime:CHHapticTimeImmediate error:&error]) {
        engine_failed(ctx, side, @"parameter update", error); return NO;
    }
    ctx->sentIntensity[side] = value.intensity; ctx->sentSharpness[side] = value.sharpness; ctx->updates[side]++;
    return YES;
}
static void handle_output(DmControllerFeedbackState *ctx, int side, dm_handle_effect value, uint64_t now) {
    if (value.intensity < 0.008f) {
        [ctx->players[side] stopAtTime:CHHapticTimeImmediate error:nil]; ctx->players[side] = nil; ctx->started[side] = 0;
        if (ctx->engines[side] && now - ctx->lastActive[side] > 2000000000ull) release_engine(ctx, side);
        return;
    }
    if (!ensure_engine(ctx, side, now)) return;
    ctx->lastActive[side] = now;
    // A 200 ms hardware lease bounds output even if the update queue stalls.
    if (!ctx->players[side] || now - ctx->started[side] >= 140000000ull) {
        NSError *error = nil;
        id<CHHapticPatternPlayer> p = [ctx->engines[side] createPlayerWithPattern:pattern error:&error];
        if (!p) { engine_failed(ctx, side, @"player creation", error); return; }
        if (!parameters(ctx, p, side, value)) return;
        if (![p startAtTime:CHHapticTimeImmediate error:&error]) { engine_failed(ctx, side, @"player start", error); return; }
        [ctx->players[side] stopAtTime:CHHapticTimeImmediate error:nil];
        ctx->players[side] = p; ctx->started[side] = now; ctx->hapticStarts[side]++;
    } else if (fabsf(value.intensity - ctx->sentIntensity[side]) >= 0.006f || fabsf(value.sharpness - ctx->sentSharpness[side]) >= 0.012f)
        parameters(ctx, ctx->players[side], side, value);
}
static void trigger_output(DmControllerFeedbackState *ctx, int side, dm_trigger_effect value, uint64_t eventSequence) {
    GCDualSenseGamepad *g = dualsense(ctx); if (!g) return;
    GCDualSenseAdaptiveTrigger *trigger = side ? g.rightTrigger : g.leftTrigger;
    // Each actual takeoff gets a new lease even if the feedback queue stalled
    // through the previous off edge. A held button cannot create an event.
    if (value.enabled && eventSequence && eventSequence != ctx->triggerEventSequence[side]) {
        ctx->triggerEventSequence[side] = eventSequence;
        dispatch_async(triggerQueue, ^{
            uint64_t token = ++ctx->triggerLease[side];
            // Constant feedback needs a fresh pull on this controller. A slow,
            // short actuator pulse strikes the finger even during a held chain.
            [trigger setModeVibrationWithStartPosition:0.05f amplitude:value.strength frequency:0.035f];
            atomic_store(&ctx->triggerStartedNs[side], now_ns());
            atomic_store(&ctx->triggerPulseSequence[side], eventSequence);
            for (int ms = 25; ms <= 50; ms += 25) {
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, ms * NSEC_PER_MSEC), triggerQueue, ^{
                    if (ctx->triggerLease[side] != token) return;
                    int mode = (int)trigger.mode, status = (int)trigger.status;
                    atomic_store(&ctx->triggerReplyMode[side], mode);
                    atomic_store(&ctx->triggerReplyStatus[side], status);
                    atomic_store(&ctx->triggerReplyArm[side], trigger.armPosition);
                    if (mode == GCDualSenseAdaptiveTriggerModeVibration &&
                        status == GCDualSenseAdaptiveTriggerStatusVibrationIsVibrating &&
                        ctx->triggerReplyToken[side] != token) {
                        ctx->triggerReplyToken[side] = token;
                        atomic_fetch_add(&ctx->triggerActiveReplies[side], 1);
                    }
                });
            }
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, DM_JUMP_TRIGGER_PULSE_NS), triggerQueue, ^{
                if (ctx->triggerLease[side] == token) {
                    ++ctx->triggerLease[side]; [trigger setModeOff];
                    atomic_store(&ctx->triggerStoppedNs[side], now_ns());
                }
            });
        });
        ctx->triggerOn[side] = YES; ctx->triggerCommands[side]++;
    } else if (!value.enabled && ctx->triggerOn[side]) {
        dispatch_async(triggerQueue, ^{
            ++ctx->triggerLease[side]; [trigger setModeOff];
            atomic_store(&ctx->triggerStoppedNs[side], now_ns());
        });
        ctx->triggerOn[side] = NO; ctx->triggerCommands[side]++;
    }
}
static void smash_trigger_output(DmControllerFeedbackState *ctx, int side, dm_smash_feedback_output value, uint64_t now) {
    GCDualSenseGamepad *g = dualsense(ctx); if (!g) return;
    GCDualSenseAdaptiveTrigger *trigger = side ? g.rightTrigger : g.leftTrigger;
    // Both the actual game mapping/held bit and live physical travel must agree.
    // Ordinary trigger presses outside a committed shield state remain neutral.
    unsigned mode = dm_smash_feedback_trigger_mode(value, side, ctx->travel[side]);
    BOOL newImpact = mode == 2 && value.impact_sequence != ctx->smashImpactSequence[side];
    if (mode == ctx->smashTriggerMode[side] && !newImpact &&
        (mode != 1 || now - ctx->smashTriggerAt[side] < 50000000ull)) return;
    ctx->smashTriggerMode[side] = mode; ctx->smashTriggerAt[side] = now;
    if (mode == 2) ctx->smashImpactSequence[side] = value.impact_sequence;
    dispatch_async(triggerQueue, ^{
        uint64_t token = ++ctx->triggerLease[side];
        if (mode == 2) {
            [trigger setModeVibrationWithStartPosition:.05f amplitude:smash_guard_impact frequency:.035f];
            atomic_store(&ctx->triggerStartedNs[side], now_ns());
            atomic_store(&ctx->triggerPulseSequence[side], value.impact_sequence);
        } else if (mode == 1) {
            [trigger setModeFeedbackWithStartPosition:.10f resistiveStrength:smash_guard_resistance];
        } else {
            [trigger setModeOff]; atomic_store(&ctx->triggerStoppedNs[side], now_ns());
        }
        if (mode) dispatch_after(dispatch_time(DISPATCH_TIME_NOW, mode == 2 ? smash_guard_pulse_ns : 150000000), triggerQueue, ^{
            if (ctx->triggerLease[side] == token) {
                ++ctx->triggerLease[side]; [trigger setModeOff];
                atomic_store(&ctx->triggerStoppedNs[side], now_ns());
            }
        });
    });
    ctx->triggerOn[side] = mode != 0; ctx->triggerCommands[side]++;
}
static void report(DmControllerFeedbackState *ctx, dm_feedback_output sample, uint64_t now) {
    if (ctx->reportAt && now - ctx->reportAt < 2000000000ull) return;
    ctx->reportAt = now;
    dm_odyssey_feedback_stats events; dm_odyssey_feedback_get_stats(&events);
    dm_smash_feedback_stats smash; dm_smash_feedback_get_stats(&smash);
    NSDictionary *r = @{
        @"player":@(ctx->player + 1), @"odysseyEventEffectsEnabled":@(odyssey_effects() && ctx->player == 0),
        @"controller":ctx->selected.vendorName ?: @"none", @"build":NSBundle.mainBundle.infoDictionary[@"CFBundleVersion"] ?: @"unknown",
        @"connected":@(ctx->selected != nil), @"foreground":@(active), @"stereoHaptics":@(ctx->stereo),
        @"adaptiveTriggers":@(dualsense(ctx) != nil), @"motionAvailable":@(ctx->selected.motion.hasRotationRate),
        @"motionSamples":@(atomic_load(&ctx->motionCount)), @"motionSamplesAccepted":@(sample.motion_samples),
        @"gameMotionReadCalls":@(sample.motion_reads), @"gameMotionStatesReturned":@(sample.motion_states_returned),
        @"nativeVibrationSendCalls":@(sample.vibration_sends),
        @"epoch":@(sample.epoch), @"nativeSequence":@[@(sample.sequence[0]), @(sample.sequence[1])],
        @"nativeNonzeroObserved":@[@(ctx->nonzero[0]), @(ctx->nonzero[1])],
        @"hapticStartsSucceeded":@[@(ctx->hapticStarts[0]), @(ctx->hapticStarts[1])],
        @"hapticParameterUpdatesSucceeded":@[@(ctx->updates[0]), @(ctx->updates[1])],
        @"triggerCommandsSubmitted":@[@(ctx->triggerCommands[0]), @(ctx->triggerCommands[1])],
        @"triggerEffectProfile":smash_effects() ? @"Smash Guard" : odyssey_effects() ? @"Odyssey takeoffs" : @"none",
        @"triggerPulseMs":@((smash_effects() ? smash_guard_pulse_ns : DM_JUMP_TRIGGER_PULSE_NS) / 1000000),
        @"triggerKickStrength":@(smash_effects() ? smash_guard_impact : .60f),
        @"triggerPulseFrequency":@0.035,
        @"triggerModeLastReported":@[@(dualsense(ctx).leftTrigger.mode), @(dualsense(ctx).rightTrigger.mode)],
        @"triggerStatusLastReported":@[@(dualsense(ctx).leftTrigger.status), @(dualsense(ctx).rightTrigger.status)],
        @"triggerArmPositionLastReported":@[@(dualsense(ctx).leftTrigger.armPosition), @(dualsense(ctx).rightTrigger.armPosition)],
        @"triggerPulseActiveReplies":@[@(atomic_load(&ctx->triggerActiveReplies[0])), @(atomic_load(&ctx->triggerActiveReplies[1]))],
        @"triggerPulseSampleMode":@[@(atomic_load(&ctx->triggerReplyMode[0])), @(atomic_load(&ctx->triggerReplyMode[1]))],
        @"triggerPulseSampleStatus":@[@(atomic_load(&ctx->triggerReplyStatus[0])), @(atomic_load(&ctx->triggerReplyStatus[1]))],
        @"triggerPulseSampleArmPosition":@[@(atomic_load(&ctx->triggerReplyArm[0])), @(atomic_load(&ctx->triggerReplyArm[1]))],
        @"triggerPulseEventSequence":@[@(atomic_load(&ctx->triggerPulseSequence[0])), @(atomic_load(&ctx->triggerPulseSequence[1]))],
        @"triggerPulseStartCommandNs":@[@(atomic_load(&ctx->triggerStartedNs[0])), @(atomic_load(&ctx->triggerStartedNs[1]))],
        @"triggerPulseStopCommandNs":@[@(atomic_load(&ctx->triggerStoppedNs[0])), @(atomic_load(&ctx->triggerStoppedNs[1]))],
        @"triggerCommandsAreNotHardwareAcknowledgements":@YES,
        @"longJumpEffectsAdmitted":@(ctx->jumps), @"longJumpObserverInstalled":@(events.installed),
        @"longJumpObserved":@(events.classic_long_jump + events.rolling_jump), @"longJumpExpired":@(events.expired),
        @"classicLongJumpObserved":@(events.classic_long_jump), @"rollingJumpObserved":@(events.rolling_jump),
        @"backflipObserved":@(events.backflip), @"backflipEffectsAdmitted":@(ctx->backflips), @"backflipTextureMs":@120,
        @"wallJumpObserved":@(events.wall_jump), @"wallJumpEffectsAdmitted":@(ctx->wallJumps), @"wallJumpTextureMs":@85,
        @"sideFlipObserved":@(events.side_flip), @"sideFlipEffectsAdmitted":@(ctx->sideFlips), @"sideFlipTextureMs":@120,
        @"takeoffsObserved":@(events.observed), @"takeoffEventsExpired":@(events.expired),
        @"smashGuardObserverInstalled":@(smash.installed), @"smashGuardMappingObservations":@(smash.mappings),
        @"smashGuardStatusTransitions":@(smash.transitions), @"smashGuardHeartbeats":@(smash.heartbeats),
        @"smashGuardImpactsForPlayer":@(smash.impacts[ctx->player]),
        @"smashGuardResistance":@(smash_guard_resistance),
        @"lastJumpEventSequence":@(ctx->jumpSequence), @"lastJumpEventKind":@(ctx->jumpKind), @"lastJumpEventNs":@(ctx->jumpAt),
        @"gameFrame":@(frameCount), @"timestampNs":@(now)};
    dispatch_async(diagnostics, ^{
        NSString *doc = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
        NSData *data = [NSJSONSerialization dataWithJSONObject:r options:NSJSONWritingPrettyPrinted error:nil];
        NSString *name = ctx->player ? [NSString stringWithFormat:@"controller-feedback-player-%u.json", ctx->player + 1] : @"controller-feedback.json";
        [data writeToFile:[doc stringByAppendingPathComponent:name] options:NSDataWritingAtomic error:nil];
    });
}
static void tick_device(DmControllerFeedbackState *ctx, uint64_t now) {
    dm_feedback_output sample; dm_feedback_poll_player(ctx->player, now, &sample);
    BOOL live = ctx->selected && active && frameAt && now >= frameAt && now - frameAt < 200000000ull;
    dm_smash_feedback_output shield = {0};
    if (smash_effects() && live) dm_smash_feedback_poll(ctx->player, now, &shield);
    dm_odyssey_feedback_event event;
    while (odyssey_effects() && ctx->player == 0 && dm_odyssey_feedback_next(&event)) {
        now = now_ns(); // The guest may publish after the tick's initial timestamp.
        if (live && (event.kind == DM_ODYSSEY_LONG_JUMP || event.kind == DM_ODYSSEY_ROLLING_JUMP ||
                     event.kind == DM_ODYSSEY_BACKFLIP || event.kind == DM_ODYSSEY_WALL_JUMP ||
                     event.kind == DM_ODYSSEY_SIDE_FLIP) && event.timestamp_ns <= now &&
            now - event.timestamp_ns < 90000000ull && event.timestamp_ns > ctx->jumpAt) {
            ctx->jumpAt = event.timestamp_ns; ctx->jumpSequence = event.sequence; ctx->jumpKind = event.kind;
            uint64_t count;
            if (event.kind == DM_ODYSSEY_BACKFLIP) count = ++ctx->backflips;
            else if (event.kind == DM_ODYSSEY_WALL_JUMP) count = ++ctx->wallJumps;
            else if (event.kind == DM_ODYSSEY_SIDE_FLIP) count = ++ctx->sideFlips;
            else count = ++ctx->jumps;
            const char *label = event.kind == DM_ODYSSEY_BACKFLIP ? "backflip" :
                event.kind == DM_ODYSSEY_WALL_JUMP ? "wall-jump" : event.kind == DM_ODYSSEY_SIDE_FLIP ? "side-flip" :
                event.kind == DM_ODYSSEY_ROLLING_JUMP ? "rolling-jump" : "long-jump";
            LOG("controller-feedback: %s kick #%llu sequence %llu", label,
                (unsigned long long)count, (unsigned long long)event.sequence);
        }
    }
    dm_handle_effect value[2] = {{0}};
    for (int side = 0; side < 2; side++) {
        if (sample.sequence[side] != ctx->lastSequence[side]) {
            ctx->lastSequence[side] = sample.sequence[side];
            if (sample.value[side].amp_low > 0.008f || sample.value[side].amp_high > 0.008f) ctx->nonzero[side]++;
        }
        if (live) {
            value[side] = dm_feedback_native_effect(sample.value[side], 0.85f);
            dm_handle_effect jump;
            switch (ctx->jumpKind) {
                case DM_ODYSSEY_BACKFLIP: jump = dm_feedback_backflip(ctx->jumpAt, now, side); break;
                case DM_ODYSSEY_WALL_JUMP: jump = dm_feedback_wall_jump(ctx->jumpAt, now, side); break;
                case DM_ODYSSEY_SIDE_FLIP: jump = dm_feedback_side_flip(ctx->jumpAt, now, side); break;
                default: jump = dm_feedback_long_jump(ctx->jumpAt, now, side); break;
            }
            if (jump.intensity > value[side].intensity) value[side] = jump;
        }
        BOOL triggerJump = ctx->jumpKind == DM_ODYSSEY_LONG_JUMP || ctx->jumpKind == DM_ODYSSEY_ROLLING_JUMP || ctx->jumpKind == DM_ODYSSEY_BACKFLIP;
        if (smash_effects()) smash_trigger_output(ctx, side, shield, now);
        else trigger_output(ctx, side, live && triggerJump ? dm_feedback_jump_trigger(ctx->jumpAt, now, ctx->travel[side]) : (dm_trigger_effect){0}, ctx->jumpSequence);
    }
    if (ctx->stereo) { handle_output(ctx, 0, value[0], now); handle_output(ctx, 1, value[1], now); }
    else { handle_output(ctx, 0, value[value[1].intensity > value[0].intensity ? 1 : 0], now); }
    report(ctx, sample, now);
}
static void tick(void) {
    uint64_t now = now_ns(), frame = dm_nvn_frame_count();
    if (frame != frameCount) { frameCount = frame; frameAt = now; dm_feedback_game_tick(now); }
    for (unsigned player = 0; player < dm_input_max_players(); ++player) tick_device(contexts[player], now);
}
static void init_feedback(void) {
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        dm_feedback_configure_players(dm_input_max_players());
        for (unsigned p = 0; p < dm_input_max_players(); ++p) {
            contexts[p] = [DmControllerFeedbackState new]; contexts[p]->player = p;
        }
        queue = dispatch_queue_create("native.controller-feedback", dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INTERACTIVE, 0));
        diagnostics = dispatch_queue_create("native.controller-diagnostics", dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_UTILITY, 0));
        triggerQueue = dispatch_queue_create("native.controller-trigger-deadlines", dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INTERACTIVE, 0));
        dispatch_queue_set_specific(queue, &queueKey, &queueKey, NULL);
        active = UIApplication.sharedApplication.applicationState == UIApplicationStateActive;
        timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, queue);
        dispatch_source_set_timer(timer, DISPATCH_TIME_FOREVER, 8 * NSEC_PER_MSEC, NSEC_PER_MSEC);
        dispatch_source_set_event_handler(timer, ^{ @autoreleasepool { tick(); } });
        dispatch_resume(timer);
    });
}
static void stop_motion(DmControllerFeedbackState *ctx) {
    atomic_store(&ctx->motionEpoch, 0);
    ctx->selected.motion.valueChangedHandler = nil;
    if (ctx->selected.motion.sensorsRequireManualActivation) ctx->selected.motion.sensorsActive = NO;
}
static void bind_motion(DmControllerFeedbackState *ctx, uint64_t epoch) {
    GCMotion *motion = ctx->selected.motion;
    if (!active || !motion.hasRotationRate) return;
    atomic_store(&ctx->motionEpoch, epoch);
    if (motion.sensorsRequireManualActivation) motion.sensorsActive = YES;
    __weak DmControllerFeedbackState *weakContext = ctx;
    motion.valueChangedHandler = ^(GCMotion *v) {
        DmControllerFeedbackState *ctx = weakContext;
        if (!ctx || atomic_load(&ctx->motionEpoch) != epoch) return;
        GCAcceleration a = v.acceleration;
        if (v.hasGravityAndUserAcceleration) { a.x = v.gravity.x + v.userAcceleration.x; a.y = v.gravity.y + v.userAcceleration.y; a.z = v.gravity.z + v.userAcceleration.z; }
        double acc[3] = {a.x, a.y, a.z}, angular[3] = {v.rotationRate.x, v.rotationRate.y, v.rotationRate.z};
        // The portable layer fuses gyro/gravity in Switch coordinates. Apple
        // attitude's reference convention need not be assumed equivalent.
        if (dm_feedback_motion_push_player(ctx->player, epoch, acc, angular, NULL, now_ns())) atomic_fetch_add(&ctx->motionCount, 1);
    };
}
static void publish_device(DmControllerFeedbackState *ctx) {
    uint64_t epoch = dm_feedback_set_player_device(ctx->player, ctx->selected != nil, active, ctx->caps, now_ns());
    if (odyssey_effects() && ctx->player == 0) dm_odyssey_feedback_set_active(ctx->selected && active);
    bind_motion(ctx, epoch);
    BOOL any = NO;
    for (unsigned p = 0; p < dm_input_max_players(); ++p) any |= contexts[p]->selected != nil;
    dispatch_source_set_timer(timer, any && active ? dispatch_time(DISPATCH_TIME_NOW, 0) : DISPATCH_TIME_FOREVER,
                             8 * NSEC_PER_MSEC, NSEC_PER_MSEC);
    ctx->reportAt = 0;
    dm_feedback_output sample; dm_feedback_poll_player(ctx->player, now_ns(), &sample); report(ctx, sample, now_ns());
}
void dm_controller_feedback_attach_player(unsigned player, GCController *controller) {
    init_feedback();
    if (player >= dm_input_max_players()) return;
    on_queue(^{
        DmControllerFeedbackState *ctx = contexts[player];
        if (ctx->selected == controller) return;
        if (odyssey_effects() && player == 0) dm_odyssey_feedback_set_active(0);
        stop_motion(ctx); quiet(ctx);
        dm_feedback_set_player_device(player, 0, active, 0, now_ns());
        ctx->selected = controller;
        NSSet *localities = controller.haptics.supportedLocalities;
        ctx->stereo = [localities containsObject:GCHapticsLocalityLeftHandle] && [localities containsObject:GCHapticsLocalityRightHandle];
        // A single default actuator mixes both authored bands in the front end.
        ctx->caps = localities.count ? DM_FEEDBACK_RUMBLE_LEFT | DM_FEEDBACK_RUMBLE_RIGHT : 0;
        if (controller.motion.hasRotationRate) ctx->caps |= DM_FEEDBACK_MOTION;
        ctx->retry[0] = ctx->retry[1] = 0; atomic_store(&ctx->motionCount, 0);
        triggers_off(ctx); publish_device(ctx);
        LOG("controller-feedback: player %u %s stereo=%d adaptive=%d motion=%d", player + 1,
            controller.vendorName.UTF8String ?: "none", ctx->stereo, dualsense(ctx) != nil, controller.motion.hasRotationRate);
    });
}
void dm_controller_feedback_attach(GCController *controller) { dm_controller_feedback_attach_player(0, controller); }
void dm_controller_feedback_focus(int foreground) {
    init_feedback();
    on_queue(^{
        if (active == (foreground != 0)) return;
        for (unsigned player = 0; player < dm_input_max_players(); ++player) { stop_motion(contexts[player]); quiet(contexts[player]); }
        active = foreground != 0; frameAt = 0;
        for (unsigned player = 0; player < dm_input_max_players(); ++player) publish_device(contexts[player]);
    });
}
void dm_controller_feedback_travel_player(unsigned player, GCController *controller, float left, float right) {
    init_feedback();
    if (player >= dm_input_max_players()) return;
    dispatch_async(queue, ^{
        DmControllerFeedbackState *ctx = contexts[player];
        if (!active || ctx->selected != controller) return;
        ctx->travel[0] = isfinite(left) ? dm_feedback_clamp(left, 0, 1) : 0;
        ctx->travel[1] = isfinite(right) ? dm_feedback_clamp(right, 0, 1) : 0;
    });
}
void dm_controller_feedback_travel(float left, float right) {
    init_feedback();
    on_queue(^{
        DmControllerFeedbackState *ctx = contexts[0];
        ctx->travel[0] = isfinite(left) ? dm_feedback_clamp(left, 0, 1) : 0;
        ctx->travel[1] = isfinite(right) ? dm_feedback_clamp(right, 0, 1) : 0;
    });
}
