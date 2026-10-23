// Optional Mac development ingress and completed-game-frame relay. No game,
// signing, account or device paths are embedded; ordinary/iOS builds are inert.
#include <TargetConditionals.h>
#if TARGET_OS_OSX
#import <Foundation/Foundation.h>
#import <ImageIO/ImageIO.h>
#import <QuartzCore/QuartzCore.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#include <CommonCrypto/CommonDigest.h>
#include <stdatomic.h>
#include <math.h>
#include <unistd.h>
#include "dm.h"
#include "dm_input.h"
#include "front.h"
#include "hle.h"
#include "smash_display.h"

// The input owner provides a virtual-only reset: physical and scripted sources
// retain their independent lifetimes, epochs and tuning.
void dm_input_reset_virtual(void);

static dispatch_queue_t relay_queue;
static dispatch_source_t relay_timer;
static NSString *relay_directory, *relay_session, *relay_viewer_session;
static uint64_t relay_sequence, relay_images, relay_input_packets, relay_rejected;
static uint64_t relay_geometry_changes, relay_input_changes, relay_capture_failures;
static double relay_last_fresh, relay_last_capture;
static int relay_lifecycle_applied;
static _Atomic int relay_started, relay_foreground, relay_pending, relay_busy;

static int relay_real(id value, double *out) {
    if (![value isKindOfClass:NSNumber.class]) return 0;
    double number = [value doubleValue];
    if (!isfinite(number)) return 0;
    *out = number; return 1;
}
static int relay_integer(id value, double lower, double upper, uint64_t *out) {
    double number;
    if (!relay_real(value, &number) || number < lower || number > upper || floor(number) != number) return 0;
    if (out) *out = (uint64_t)number;
    return 1;
}
static int relay_axis(id value, int32_t *out) {
    double number;
    if (!relay_real(value, &number) || number < -32767 || number > 32767 || floor(number) != number) return 0;
    *out = (int32_t)number; return 1;
}
typedef struct {
    double width, height, scale, insets[4];
    uint64_t sequence, buttons, geometry_changes, input_changes;
    int orientation, foreground;
    int32_t lx, ly, rx, ry;
} relay_input;
static int relay_parse(NSDictionary *json, relay_input *input) {
    uint64_t schema, orientation, foreground;
    if (![json isKindOfClass:NSDictionary.class] ||
        !relay_integer(json[@"schema"], 1, 1, &schema) ||
        ![json[@"session"] isKindOfClass:NSString.class] || ![json[@"session"] length] || [json[@"session"] length] > 128 ||
        !relay_integer(json[@"sequence"], 1, 9007199254740991.0, &input->sequence) ||
        !relay_integer(json[@"foreground_active"], 0, 1, &foreground) ||
        !relay_real(json[@"width"], &input->width) || !relay_real(json[@"height"], &input->height) ||
        !relay_real(json[@"scale"], &input->scale) ||
        input->width <= 0 || input->height <= 0 || input->width > 16384 || input->height > 16384 ||
        input->scale <= 0 || input->scale > 8 ||
        !relay_integer(json[@"interface_orientation"], 3, 4, &orientation) ||
        !relay_integer(json[@"buttons"], 0, 65535, &input->buttons) ||
        !relay_axis(json[@"lx"], &input->lx) || !relay_axis(json[@"ly"], &input->ly) ||
        !relay_axis(json[@"rx"], &input->rx) || !relay_axis(json[@"ry"], &input->ry)) return 0;
    id insets = json[@"safe_insets"];
    if (![insets isKindOfClass:NSArray.class] || [insets count] != 4) return 0;
    for (unsigned i = 0; i < 4; i++) if (!relay_real(insets[i], &input->insets[i]) || input->insets[i] < 0) return 0;
    if (input->insets[0] + input->insets[2] >= input->height || input->insets[1] + input->insets[3] >= input->width) return 0;
    input->orientation = (int)orientation; input->foreground = (int)foreground;
    // Optional diagnostic counts never establish received input freshness.
    if (json[@"geometry_changes"] && !relay_integer(json[@"geometry_changes"], 0, 9007199254740991.0, &input->geometry_changes)) return 0;
    if (json[@"input_changes"] && !relay_integer(json[@"input_changes"], 0, 9007199254740991.0, &input->input_changes)) return 0;
    return 1;
}
static void relay_active(int active) {
    int previous = atomic_exchange(&relay_foreground, active != 0);
    if (!active) {
        // A cancelled request has no renderer completion to release its slot.
        // If the renderer already took it, that in-flight copy still owns busy.
        if (atomic_exchange(&relay_pending, 0)) atomic_store(&relay_busy, 0);
        dm_input_reset_virtual();
    }
    if (previous == (active != 0) && relay_lifecycle_applied) return;
    relay_lifecycle_applied = 1;
    if (active) {
        dm_gfx_suspend(0); dm_audio_suspend(0); dm_focus_set(1);
    } else {
        dm_focus_set(3); dm_audio_suspend(1); dm_gfx_suspend(1);
    }
}
static void relay_tick(double now) {
    NSString *path = [relay_directory stringByAppendingPathComponent:@"scene-input.json"];
    NSData *data = [NSData dataWithContentsOfFile:path options:NSDataReadingMappedIfSafe error:nil];
    NSDictionary *json = data && data.length < 65536 ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    relay_input input = {0};
    if (json && relay_parse(json, &input)) {
        NSString *viewer_session = json[@"session"];
        BOOL new_session = ![viewer_session isEqualToString:relay_viewer_session];
        if (new_session || input.sequence > relay_sequence) {
            if (dm_smash_display_geometry(input.width, input.height, input.scale,
                    input.insets[0], input.insets[1], input.insets[2], input.insets[3], input.orientation)) {
                if (new_session) dm_input_reset_virtual();
                relay_viewer_session = [viewer_session copy]; relay_sequence = input.sequence;
                relay_last_fresh = now; relay_input_packets++;
                relay_geometry_changes = input.geometry_changes; relay_input_changes = input.input_changes;
                relay_active(input.foreground);
                if (input.foreground) dm_input_set(input.buttons, input.lx, input.ly, input.rx, input.ry);
            } else relay_rejected++;
        }
    } else if (data) relay_rejected++;
    // Re-reading the same atomic file/sequence cannot renew a held input lease.
    if (relay_last_fresh && now - relay_last_fresh > .250) relay_active(0);
    if (atomic_load(&relay_foreground) && now - relay_last_capture >= 1.0 / 15.0) {
        int expected = 0;
        if (atomic_compare_exchange_strong(&relay_busy, &expected, 1)) {
            relay_last_capture = now; atomic_store(&relay_pending, 1);
        }
    }
}
int dm_smash_relay_offscreen(void) { return atomic_load(&relay_started); }
int dm_smash_relay_foreground(void) { return atomic_load(&relay_foreground); }
int dm_smash_relay_capture_requested(void) { return atomic_exchange(&relay_pending, 0); }
static NSString *relay_sha256(NSData *data) {
    uint8_t digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
    char hex[CC_SHA256_DIGEST_LENGTH * 2 + 1];
    for (unsigned i = 0; i < sizeof digest; i++) snprintf(hex + 2 * i, 3, "%02x", digest[i]);
    return @(hex);
}
static NSDictionary *relay_manifest(const dm_smash_display_frame *source, uint64_t ticket, NSData *jpeg, size_t width, size_t height) {
    double aspect = source->geometry.aspect;
    BOOL geometry_available = source->frame && source->geometry.generation && isfinite(aspect) && aspect > 0 &&
        isfinite(source->geometry.width) && isfinite(source->geometry.height) && source->geometry.width > 0 && source->geometry.height > 0;
    BOOL camera_available = geometry_available && source->camera_calls && isfinite(source->camera_aspect) && source->camera_aspect > 0;
    BOOL hud_available = geometry_available && source->ui_accepted && isfinite(source->hud_aspect) && source->hud_aspect > 0;
    BOOL aspect_matches = geometry_available && fabs((double)width - height * aspect) <= 1.0;
    BOOL camera_matches = camera_available && source->camera_enabled && source->camera_generation == source->geometry.generation && fabs(source->camera_aspect - aspect) < 1.e-5;
    BOOL hud_matches = hud_available && source->hud_enabled && source->hud_generation == source->geometry.generation && fabs(source->hud_aspect - aspect) < 1.e-5;
    NSMutableArray *insets = [NSMutableArray new];
    for (unsigned i = 0; i < 4; i++) [insets addObject:isfinite(source->geometry.insets[i]) ? @(source->geometry.insets[i]) : NSNull.null];
    return @{
        @"schema": @1, @"game": @"Super Smash Bros. Ultimate", @"session": relay_session,
        @"pid": @(getpid()), @"relay_images": @(relay_images + 1), @"backend_presents": @(ticket),
        @"width": @(width), @"height": @(height), @"source_aspect": isfinite(aspect) ? @(aspect) : NSNull.null,
        @"source_geometry_generation": @(source->geometry.generation), @"source_safe_insets": insets,
        @"frame_sha256": relay_sha256(jpeg), @"source_frame": @(source->frame),
        @"camera": @{@"available": @(camera_available), @"enabled": @(source->camera_enabled),
            @"aspect": camera_available ? @(source->camera_aspect) : NSNull.null,
            @"generation": @(source->camera_generation), @"matches_source": @(camera_matches)},
        @"hud": @{@"available": @(hud_available), @"enabled": @(source->hud_enabled),
            @"aspect": hud_available ? @(source->hud_aspect) : NSNull.null,
            @"generation": @(source->hud_generation), @"matches_source": @(hud_matches)},
        @"diagnostics": @{
            @"scope": @"Actual completed native Mac gameplay / Duo development preview; no Simulator GPU rendering",
            @"source_metadata_available": @(geometry_available), @"jpeg_aspect_matches_source": @(aspect_matches),
            @"receiving_frame_binding_matches": @(aspect_matches && camera_matches && hud_matches),
            @"source_scene_width_points": @(source->geometry.width), @"source_scene_height_points": @(source->geometry.height),
            @"source_scale": @(source->geometry.scale), @"source_orientation": @(source->geometry.orientation),
            @"camera_calls_cumulative": @(source->camera_calls), @"ui_accepted": @(source->ui_accepted),
            @"ui_declined": @(source->ui_declined), @"ui_borrowed": @(source->ui_borrowed),
            @"ui_restored": @(source->ui_restored), @"ui_pose_changes": @(source->ui_pose_changes),
            @"ui_matrix_calls": @(source->ui_matrix_calls), @"ui_matrix_writes": @(source->ui_matrix_writes),
            @"projection_generation": @(source->projection_generation), @"projection_failures": @(source->projection_failures),
            @"generated_frame": @NO},
        @"transport_status": @{
            @"scope": @"Current ingress/publication telemetry; not source-frame evidence",
            @"viewer_session": relay_viewer_session ?: @"unavailable", @"viewer_sequence": @(relay_sequence),
            @"viewer_foreground_active": @(atomic_load(&relay_foreground)), @"input_packets": @(relay_input_packets),
            @"rejected_packets": @(relay_rejected), @"viewer_geometry_changes": @(relay_geometry_changes),
            @"viewer_input_changes": @(relay_input_changes), @"capture_failures": @(relay_capture_failures),
            @"published_time": @(CACurrentMediaTime())}
    };
}
void dm_smash_relay_completed(CGImageRef image, const dm_smash_display_frame *source, uint64_t ticket) {
    if (!atomic_load(&relay_started) || !relay_queue) return;
    dm_smash_display_frame frozen = {0};
    if (source) frozen = *source;
    CGImageRef owned = image ? CGImageRetain(image) : NULL;
    dispatch_async(relay_queue, ^{ @autoreleasepool {
        if (!owned) { relay_capture_failures++; atomic_store(&relay_busy, 0); return; }
        NSMutableData *jpeg = [NSMutableData new];
        CGImageDestinationRef destination = CGImageDestinationCreateWithData((__bridge CFMutableDataRef)jpeg,
            (__bridge CFStringRef)UTTypeJPEG.identifier, 1, NULL);
        if (destination) CGImageDestinationAddImage(destination, owned,
            (__bridge CFDictionaryRef)@{(__bridge NSString *)kCGImageDestinationLossyCompressionQuality: @0.88});
        BOOL encoded = destination && CGImageDestinationFinalize(destination);
        if (destination) CFRelease(destination);
        if (encoded) {
            NSDictionary *manifest = relay_manifest(&frozen, ticket, jpeg, CGImageGetWidth(owned), CGImageGetHeight(owned));
            NSData *json = [NSJSONSerialization dataWithJSONObject:manifest options:NSJSONWritingSortedKeys error:nil];
            NSString *image_path = [relay_directory stringByAppendingPathComponent:@"frame.jpg"];
            NSString *manifest_path = [relay_directory stringByAppendingPathComponent:@"backend.json"];
            if (json && [jpeg writeToFile:image_path options:NSDataWritingAtomic error:nil] &&
                [json writeToFile:manifest_path options:NSDataWritingAtomic error:nil]) relay_images++;
            else relay_capture_failures++;
        } else relay_capture_failures++;
        CGImageRelease(owned); atomic_store(&relay_busy, 0);
    } });
}
void dm_smash_relay_start(void) {
    const char *path = getenv("DM_DUO_RELAY");
    if (!path || !*path || !dm_smash_display_enabled() || atomic_exchange(&relay_started, 1)) return;
    relay_directory = [[NSString stringWithUTF8String:path] stringByStandardizingPath];
    BOOL directory = NO;
    if (![relay_directory isAbsolutePath] || ![NSFileManager.defaultManager fileExistsAtPath:relay_directory isDirectory:&directory] || !directory) {
        atomic_store(&relay_started, 0); relay_directory = nil; return;
    }
    relay_session = NSUUID.UUID.UUIDString;
    relay_queue = dispatch_queue_create("dm.smash.duo-relay", DISPATCH_QUEUE_SERIAL);
    relay_timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, relay_queue);
    dispatch_source_set_timer(relay_timer, dispatch_time(DISPATCH_TIME_NOW, 0), NSEC_PER_SEC / 60, NSEC_PER_MSEC);
    dispatch_source_set_event_handler(relay_timer, ^{ @autoreleasepool { relay_tick(CACurrentMediaTime()); } });
    dispatch_resume(relay_timer);
    LOG("Smash development relay enabled: actual Mac game backend, independent offscreen composition, isolated input lease");
}
#endif
