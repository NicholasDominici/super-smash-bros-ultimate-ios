// Virtual Nintendo-position P1 controls and independently assigned physical players.
// The host merges touch only into P1; physical callbacks carry their slot epoch.
//   Odyssey-derived geometry and per-primitive opacity come from dm_touch_controls.h.
//   A top-centre gear tap opens supported gyro/device-feedback settings on release.
//   Full controls are always available; legacy DmPadLayout values are
//   ignored without modifying stored preferences.
//   Top corners ZL above L (one column), ZR above R likewise, teardrops with the tip toward the screen corner; − and + side by side at the top centre; the left stick in the bottom-left corner (fixed ring, tilt measured from the ring centre, small dead zone);
//     the A (right) B (bottom) X (top) Y (left) diamond in the bottom-right corner, sliding a finger between keys switches keys. Each bottom corner holds a single control, so it sits close in (reaching halfway into the side safe-area inset).
//   A D-pad (inward of and below the left stick, 8-way), a right stick that is not drawn
//     (a touch landing in the right third of the screen on no control holds it: centred where it lands, the centre dragged along once the finger passes the stick radius) and L3 / R3 (small round keys in the top row, inward of ZL / ZR).
//     Breath of the Wild crouches with L3 and uses the scope with R3; 3D World and Breath of the Wild turn the camera with the right stick.
//   Touch-down ownership: exclusive gear first, then locked keys (shoulders,
//   − / +, L3 / R3), then the nearest diamond, D-pad or left-stick grab circle,
//     then the right stick for a touch in the right third.
//   Everything hugs the edges and corners to leave the picture room; controls sit over the picture, one CAShapeLayer each: a press only swaps the fill, a stick only moves its knob, nothing redraws the whole screen.
//   Touches no control takes go to the game's touch screen (pushGame).
//   Gameplay controls hide when physical P1 is connected; the gear remains
//   available. Unclaimed touches still reach the game. Physical controllers map
//   by position: bottom = B, right = A, left = Y, top = X.
#import <UIKit/UIKit.h>
#import <GameController/GameController.h>
#import <CoreText/CoreText.h>
#import <QuartzCore/QuartzCore.h>
#include <pthread.h>
#include "dm_input.h"
#include "dm_touch_controls.h"
#include "dm_display_geometry.h"
#include "smash_display.h"
#include "front.h"
#include "game_profile.h"
#import "DmControllerFeedback.h"
#include <stdatomic.h>

enum { B_A = 0, B_B, B_X, B_Y, B_LS, B_RS, B_L, B_R, B_ZL, B_ZR, B_PLUS, B_MINUS, B_LEFT, B_UP, B_RIGHT, B_DOWN, B_N };
enum { C_NONE = 0, C_STICK, C_DPAD, C_FACE, C_BTN, C_SETTINGS, C_GAME };   // ownership is retained until a touch ends; settings touches never reach gameplay

static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;
static uint64_t g_touch_btn;
static int32_t g_touch_lx, g_touch_ly, g_touch_rx, g_touch_ry;
static GCController *g_pads[DM_INPUT_MAX_PLAYERS];
static uint64_t g_pad_btn[DM_INPUT_MAX_PLAYERS], g_pad_epoch[DM_INPUT_MAX_PLAYERS];
static BOOL g_pad_active;
// HID may swap players on a guest thread. Only the main queue touches the
// framework indicator hints; delayed work looks up current identities again.
static void update_pad_indicators(void) {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!g_pad_active) return;
        for (unsigned p = 0; p < dm_input_max_players(); ++p) {
            GCController *controller = g_pads[p];
            if (!controller) continue;
            unsigned logical = dm_pad_logical_player(p);
            controller.playerIndex = logical < 4 ? (GCControllerPlayerIndex)logical : GCControllerPlayerIndexUnset;
        }
    });
}
static void publish(void) {
    pthread_mutex_lock(&g_mu);
    dm_input_set(g_touch_btn, g_touch_lx, g_touch_ly, g_touch_rx, g_touch_ry);
    pthread_mutex_unlock(&g_mu);
}

// ---- Canonical layout constants (in u; the right half mirrors) ----
static const CGFloat
    K_ZL_R = DM_TC_ZL_R, K_L_R = DM_TC_L_R, K_DROP_TIP = DM_TC_DROP_TIP,
    K_FACE_GAP = DM_TC_FACE_GAP, K_FACE_R = DM_TC_FACE_R,
    K_STICK_R = DM_TC_STICK_R, K_KNOB_R = DM_TC_KNOB_R,
    K_STICK_GRAB = DM_TC_STICK_GRAB, K_FULL = DM_TC_FULL, K_DEAD = DM_TC_DEAD,
    K_DPAD_R = DM_TC_DPAD_R, K_ARM_W = DM_TC_ARM_W, K_ARM_IN = DM_TC_ARM_IN,
    K_DPAD_GRAB = DM_TC_DPAD_GRAB, K_RSTICK_R = DM_TC_RSTICK_R,
    K_RSWIPE = DM_TC_RSWIPE, K_CLICK_R = DM_TC_CLICK_R;
static const int k_btns[] = {B_ZL, B_L, B_ZR, B_R, B_MINUS, B_PLUS, B_LS, B_RS};   // keys locked at touch-down

// Smash has no device-motion or local Core Haptics sink yet. These switches
// must not claim support or write preferences for a backend that does not exist.
@interface DmSettingsController : UITableViewController <UIAdaptivePresentationControllerDelegate>
@property(nonatomic, copy) void (^onClose)(void);
@end
@implementation DmSettingsController
- (void)viewDidLoad {
    [super viewDidLoad]; self.title = @"Settings";
    self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(closeSettings:)];
    self.tableView.rowHeight = 76;
}
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { (void)tableView; (void)section; return 3; }
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    (void)tableView;
    static NSString *const titles[] = {@"Gyro", @"Device haptics", @"Also with controller"};
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    cell.textLabel.text = titles[indexPath.row];
    cell.detailTextLabel.text = indexPath.row == 2 ? @"Requires device haptics" : @"Unavailable in this Smash build";
    cell.detailTextLabel.numberOfLines = 0; cell.selectionStyle = UITableViewCellSelectionStyleNone;
    UISwitch *toggle = [UISwitch new]; toggle.on = NO; toggle.enabled = NO;
    toggle.accessibilityLabel = titles[indexPath.row]; toggle.accessibilityHint = cell.detailTextLabel.text;
    cell.accessoryView = toggle;
    cell.isAccessibilityElement = NO; cell.accessibilityElements = @[toggle];
    return cell;
}
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    (void)tableView; (void)section; return @"Supported controller haptics stay enabled.";
}
- (void)closeSettings:(UIBarButtonItem *)sender {
    (void)sender; [self dismissViewControllerAnimated:YES completion:self.onClose];
}
- (void)presentationControllerDidDismiss:(UIPresentationController *)presentationController {
    (void)presentationController; if (self.onClose) self.onClose();
}
@end

@interface DmGamepad : UIView
- (BOOL)openSettingsFromAccessibility:(UIAccessibilityCustomAction *)action;
@end
static __weak DmGamepad *g_view;

// The drawn controls are layers. Expose the gear as a real accessible button
// without giving its touch to a second UIKit responder or a gameplay handler.
@interface DmSettingsAccessibility : UIAccessibilityElement
@property(nonatomic, copy) BOOL (^openSettings)(void);
@end
@implementation DmSettingsAccessibility
- (BOOL)accessibilityActivate { return self.openSettings ? self.openSettings() : NO; }
@end

@implementation DmGamepad {
    NSMapTable<UITouch *, NSNumber *> *_owner;     // touch → control (with the key for C_BTN or the stick for C_STICK, << 8)
    UITouch *_stick[2]; CGPoint _stickNow[2];      // the touch holding each stick and where it is now (0 left, 1 right)
    CGPoint _rCentre;                              // the right stick's centre: where its touch landed, dragged along past K_RSTICK_R
    uint64_t _faceBits, _dpadBits, _btnBits;
    NSMapTable<UITouch *, NSNumber *> *_faceOf;    // which keys each touch on the diamond currently holds
    CAShapeLayer *_key[B_N]; CATextLayer *_label[B_N];   // one layer per key
    CAShapeLayer *_ring, *_knob;                   // the left stick (the right one is not drawn)
    UIImageView *_gearIcon;
    DmSettingsAccessibility *_gearAccessibility;
    dm_tc_gear _settingsGesture;
    uint64_t _settingsToken;
    UITouch *_settingsTouch;
    BOOL _settingsVisible, _layoutValid;
    CGRect _previousBounds; UIEdgeInsets _previousInsets;
    BOOL _stickShown;                              // the left stick was held at the last refresh
    CALayer *_controls;                            // holds every control layer: hidden while a physical controller is connected (the view itself stays, for game touches)
    BOOL _padOff;                                  // a physical controller is connected: every touch goes to the game
    UITouch *_game[16];                            // touches on the game's touch screen by finger slot
}

static UIColor *k_idle, *k_on, *k_line, *k_ringFill, *k_text, *k_textOn;
static CAShapeLayer *shape(CALayer *parent) {
    CAShapeLayer *l = [CAShapeLayer layer];
    l.fillColor = k_idle.CGColor; l.strokeColor = k_line.CGColor; l.lineWidth = 1.5;
    l.shadowColor = UIColor.blackColor.CGColor; l.shadowOpacity = DM_TC_SHADOW_ALPHA; l.shadowRadius = 3; l.shadowOffset = CGSizeMake(0, 1);
    [parent addSublayer:l]; return l;
}
static CATextLayer *label(CALayer *parent, NSString *s) {
    CATextLayer *t = [CATextLayer layer];
    t.string = s; t.alignmentMode = kCAAlignmentCenter; t.foregroundColor = k_text.CGColor;
    [parent addSublayer:t]; return t;
}

- (instancetype)initWithFrame:(CGRect)f {
    if ((self = [super initWithFrame:f])) {
        self.multipleTouchEnabled = YES; self.opaque = NO; self.backgroundColor = UIColor.clearColor;
        _owner = [NSMapTable strongToStrongObjectsMapTable]; _faceOf = [NSMapTable strongToStrongObjectsMapTable];
        static dispatch_once_t once;
        dispatch_once(&once, ^{
            // each colour carries its own low opacity instead of lowering the whole view's alpha (that would add an off-screen pass for the full-screen layer)
            k_idle = [UIColor colorWithWhite:1 alpha:DM_TC_IDLE_ALPHA]; k_on = [UIColor colorWithWhite:1 alpha:DM_TC_PRESSED_ALPHA]; k_line = [UIColor colorWithWhite:1 alpha:DM_TC_STROKE_ALPHA];
            k_ringFill = [UIColor colorWithWhite:1 alpha:DM_TC_RING_ALPHA]; k_text = [UIColor colorWithWhite:1 alpha:DM_TC_TEXT_ALPHA]; k_textOn = [UIColor colorWithWhite:1 alpha:DM_TC_PRESSED_TEXT_ALPHA];
        });
        _controls = [CALayer layer]; [self.layer addSublayer:_controls];
        _ring = shape(_controls); _ring.fillColor = k_ringFill.CGColor;
        _knob = shape(_controls);
        CAShapeLayer *in = [CAShapeLayer layer]; in.fillColor = nil; in.strokeColor = k_line.CGColor; in.lineWidth = 1.5;   // inner ring of the knob
        [_knob addSublayer:in];
        static NSString *const names[B_N] = {@"A", @"B", @"X", @"Y", @"L3", @"R3", @"L", @"R", @"ZL", @"ZR", @"+", @"−"};
        for (int b = 0; b < B_N; b++) {
            _key[b] = shape(_controls);
            if (names[b]) _label[b] = label(_key[b], names[b]);   // the D-pad arms carry no label
        }
        _gearIcon = [[UIImageView alloc] initWithImage:[UIImage systemImageNamed:@DM_TC_GEAR_SYMBOL withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:DM_TC_GEAR_ICON_SIZE weight:DM_TC_GEAR_REGULAR_WEIGHT ? UIImageSymbolWeightRegular : UIImageSymbolWeightSemibold]]];
        _gearIcon.contentMode = UIViewContentModeCenter; _gearIcon.tintColor = [UIColor colorWithWhite:1 alpha:DM_TC_GEAR_ALPHA];
        _gearIcon.userInteractionEnabled = NO;
        [self addSubview:_gearIcon];
        _gearAccessibility = [[DmSettingsAccessibility alloc] initWithAccessibilityContainer:self];
        _gearAccessibility.accessibilityLabel = @"Settings";
        _gearAccessibility.accessibilityHint = @"Tap to open, or use the Open settings action.";
        _gearAccessibility.accessibilityTraits = UIAccessibilityTraitButton;
        __weak DmGamepad *weakSelf = self;
        _gearAccessibility.openSettings = ^BOOL { return [weakSelf openSettingsFromAccessibility:nil]; };
        _gearAccessibility.accessibilityCustomActions = @[[[UIAccessibilityCustomAction alloc] initWithName:@"Open settings" target:self selector:@selector(openSettingsFromAccessibility:)]];
        self.accessibilityElements = @[_gearAccessibility];
        NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
        [nc addObserver:self selector:@selector(padsChanged) name:GCControllerDidConnectNotification object:nil];
        [nc addObserver:self selector:@selector(padsChanged) name:GCControllerDidDisconnectNotification object:nil];
        [nc addObserver:self selector:@selector(suspendPads) name:UIApplicationWillResignActiveNotification object:nil];
        [nc addObserver:self selector:@selector(resumePads) name:UIApplicationDidBecomeActiveNotification object:nil];
        g_pad_active = UIApplication.sharedApplication.applicationState == UIApplicationStateActive;
        dm_pad_set_assignment_callback(update_pad_indicators);
        [self padsChanged];
    }
    return self;
}
// ---- Deliberate, exclusive settings access ----
static uint64_t settingsNow(void) { return (uint64_t)(CACurrentMediaTime() * 1e9); }
- (void)finishSettings {
    _settingsVisible = NO;
    [self reset];   // A touch held across a menu change must begin again.
}
- (BOOL)openSettings {
    if (_settingsVisible || !self.window || UIApplication.sharedApplication.applicationState != UIApplicationStateActive) return NO;
    UIViewController *controller = self.window.rootViewController;
    if (!controller || controller.presentedViewController) return NO;
    [self reset];
    _settingsVisible = YES;
    DmSettingsController *menu = [[DmSettingsController alloc] initWithStyle:UITableViewStyleInsetGrouped];
    __weak DmGamepad *weakSelf = self;
    menu.onClose = ^{ [weakSelf finishSettings]; };
    UINavigationController *navigation = [[UINavigationController alloc] initWithRootViewController:menu];
    navigation.modalPresentationStyle = UIModalPresentationPageSheet;
    navigation.preferredContentSize = CGSizeMake(420, 390);
    navigation.sheetPresentationController.detents = @[UISheetPresentationControllerDetent.mediumDetent, UISheetPresentationControllerDetent.largeDetent];
    navigation.sheetPresentationController.prefersGrabberVisible = YES;
    navigation.presentationController.delegate = menu;
    [controller presentViewController:navigation animated:YES completion:nil];
    return YES;
}
- (BOOL)openSettingsFromAccessibility:(UIAccessibilityCustomAction *)action {
    (void)action;
    return [self openSettings];
}
- (void)checkSettingsMovementForTouch:(UITouch *)touch event:(UIEvent *)event {
    // UIKit may combine a rapid excursion and return into one move callback.
    // Every historical sample must pass; a later endpoint cannot clear a block.
    for (UITouch *sample in [event coalescedTouchesForTouch:touch]) {
        CGPoint p = [sample locationInView:self];
        dm_tc_gear_move(&_settingsGesture, (dm_tc_point){p.x, p.y});
        if (![self inSettings:p]) dm_tc_gear_block(&_settingsGesture);
    }
    CGPoint p = [touch locationInView:self];
    dm_tc_gear_move(&_settingsGesture, (dm_tc_point){p.x, p.y});
    if (![self inSettings:p]) dm_tc_gear_block(&_settingsGesture);
}
- (void)beginSettingsTouch:(UITouch *)touch blocked:(BOOL)blocked {
    [_owner setObject:@(C_SETTINGS) forKey:touch];
    if (_settingsTouch) { dm_tc_gear_block(&_settingsGesture); return; }
    _settingsTouch = touch;
    CGPoint p = [touch locationInView:self];
    _settingsToken = dm_tc_gear_begin(&_settingsGesture, (dm_tc_point){p.x, p.y}, settingsNow(), blocked);
}

// ---- Layout (points; computed inside the safe area) ----
- (dm_tc_layout)touchLayout { UIEdgeInsets i = self.safeAreaInsets;
    return dm_tc_make_layout(self.bounds.size.width, self.bounds.size.height, (dm_tc_insets){i.top, i.left, i.bottom, i.right}); }
static CGPoint uiPoint(dm_tc_point p) { return CGPointMake(p.x, p.y); }
static CGRect uiRect(dm_tc_rect r) { return CGRectMake(r.x, r.y, r.width, r.height); }
- (CGFloat)u { return [self touchLayout].unit; }
- (CGPoint)faceCenter { return uiPoint([self touchLayout].face); }
- (CGFloat)faceGap { return K_FACE_GAP * self.u; }
- (CGFloat)faceR { return K_FACE_R * self.u; }
- (CGPoint)facePos:(int)b { return uiPoint(dm_tc_face_position([self touchLayout], b)); }
- (CGPoint)stickHome { return uiPoint([self touchLayout].left_stick); }
- (CGPoint)stickCentre:(int)i { return i ? _rCentre : self.stickHome; }
- (CGFloat)stickR:(int)i { return (i ? K_RSTICK_R : K_STICK_R) * self.u; }
- (BOOL)inRightArea:(CGPoint)p { CGRect b = self.bounds; return p.x >= CGRectGetMaxX(b) - b.size.width * K_RSWIPE; }
- (CGPoint)dpadCenter { return uiPoint([self touchLayout].dpad); }
- (CGFloat)dpadR { return K_DPAD_R * self.u; }
static BOOL isDrop(int b) { return b == B_ZL || b == B_L || b == B_ZR || b == B_R; }
static BOOL isClick(int b) { return b == B_LS || b == B_RS; }
- (CGPoint)dropCenter:(int)b { return uiPoint(dm_tc_shoulder([self touchLayout], b == B_ZR || b == B_R, b == B_ZL || b == B_ZR)); }
- (CGFloat)dropR:(int)b { return (b == B_ZL || b == B_ZR ? K_ZL_R : K_L_R) * self.u; }
- (CGPoint)clickCenter:(int)b { return uiPoint(dm_tc_click([self touchLayout], b == B_RS)); }
- (CGRect)pillRect:(int)b { return uiRect(dm_tc_pill([self touchLayout], b == B_PLUS)); }
- (BOOL)inSettings:(CGPoint)p { return dm_tc_contains([self touchLayout].gear, (dm_tc_point){p.x, p.y}); }

static CGFloat dist(CGPoint a, CGPoint b) { return hypot(a.x - b.x, a.y - b.y); }
- (int)btnAt:(CGPoint)p {   // locked keys (tested on touch-down only, then locked)
    CGFloat u = self.u;
    for (int i = 0; i < (int)(sizeof k_btns / sizeof *k_btns); i++) { int b = k_btns[i];
        BOOL hit = isDrop(b) ? dist(p, [self dropCenter:b]) <= [self dropR:b] * 1.35
                 : isClick(b) ? dist(p, [self clickCenter:b]) <= K_CLICK_R * u * 1.35
                 : dm_tc_contains(dm_tc_pill_hit([self touchLayout], b == B_PLUS), (dm_tc_point){p.x,p.y});
        if (hit) return b; }
    return -1;
}
- (uint64_t)faceAt:(CGPoint)p {   // keys under the finger in the diamond (between two keys both count)
    uint64_t m = 0; CGFloat r = self.faceR * 1.25;
    for (int b = B_A; b <= B_Y; b++) if (dist(p, [self facePos:b]) <= r) m |= 1ull << b;
    return m;
}
- (uint64_t)dpadAt:(CGPoint)p {   // 8 directions: 45° each, diagonals press two keys; a small centre circle counts as none
    CGPoint c = self.dpadCenter; CGFloat dx = p.x - c.x, dy = p.y - c.y;
    if (hypot(dx, dy) < self.dpadR * 0.25) return 0;
    double a = atan2(-dy, dx) * 180 / M_PI; uint64_t m = 0;
    if (a > -67.5 && a < 67.5) m |= 1ull << B_RIGHT;
    if (a > 22.5 && a < 157.5) m |= 1ull << B_UP;
    if (a > 112.5 || a < -112.5) m |= 1ull << B_LEFT;
    if (a < -22.5 && a > -157.5) m |= 1ull << B_DOWN;
    return m;
}
- (CGPoint)knobOffset:(int)i {   // knob offset from the stick centre (clamped to the stick radius)
    if (!_stick[i]) return CGPointZero;
    CGPoint h = [self stickCentre:i]; CGFloat dx = _stickNow[i].x - h.x, dy = _stickNow[i].y - h.y, d = hypot(dx, dy), R = [self stickR:i];
    if (d > R) { dx *= R / d; dy *= R / d; }
    return CGPointMake(dx, dy);
}

// ---- Touch ----
- (void)recompute {
    uint64_t face = 0; for (UITouch *t in _faceOf) face |= [_faceOf objectForKey:t].unsignedLongLongValue;
    uint64_t btn = 0, dpad = 0;
    for (UITouch *t in _owner) { uint64_t v = [_owner objectForKey:t].unsignedLongLongValue; int c = (int)(v & 0xff);
        if (c == C_BTN) btn |= 1ull << (v >> 8);
        else if (c == C_DPAD) dpad |= [self dpadAt:[t locationInView:self]]; }
    int32_t ax[4] = {0};
    for (int i = 0; i < 2; i++) {
        CGPoint o = [self knobOffset:i]; CGFloat R = [self stickR:i], d = hypot(o.x, o.y), dz = R * K_DEAD;
        if (d <= dz) continue;
        CGFloat m = fmin((d - dz) / (R * K_FULL - dz), 1) / d;   // outside the dead zone: 0 rising to full at the full-tilt radius
        ax[i * 2] = (int32_t)lrint(o.x * m * 32767); ax[i * 2 + 1] = (int32_t)lrint(-o.y * m * 32767);   // host: up is positive; rounded so full tilt is exactly 32767
    }
    BOOL changed = face != _faceBits || dpad != _dpadBits || btn != _btnBits;
    _faceBits = face; _dpadBits = dpad; _btnBits = btn;
    pthread_mutex_lock(&g_mu);
    g_touch_btn = face | dpad | btn; g_touch_lx = ax[0]; g_touch_ly = ax[1]; g_touch_rx = ax[2]; g_touch_ry = ax[3];
    pthread_mutex_unlock(&g_mu);
    publish();
    BOOL stick = _stick[0] != nil;   // only the left stick is drawn: the right one needs no refresh
    if (changed || stick || _stickShown) [self refresh];   // also refresh on the stick release so the knob returns to the centre
    _stickShown = stick;
}
// Touches no control takes (all of them while a physical controller is connected) go to the game's touch screen, normalized on the 16:9 picture that front_ios.m
// centres in the screen: Super Mario Galaxy's pointer in handheld mode (profile op_mode). The host reports them only in handheld mode, as on the Switch (hle_hid.c touch_read)
- (void)pushGame {
    CGRect b = self.bounds;
    dm_display_geometry geometry = dm_display_make(b.size.width, b.size.height,
                                                   self.window.screen.nativeScale, dm_smash_display_scene_aspect());
    if (!geometry.valid || !isfinite(b.origin.x) || !isfinite(b.origin.y)) {
        dm_touch_set(NULL, 0); // A transient empty scene must release the prior guest contact.
        return;
    }
    CGFloat w = geometry.picture.width, h = geometry.picture.height;
    CGFloat x0 = b.origin.x + geometry.picture.x, y0 = b.origin.y + geometry.picture.y;
    dm_touch t[16]; int n = 0;
    for (int i = 0; i < 16; i++) if (_game[i]) {
        CGPoint p = [_game[i] locationInView:self];
        t[n++] = (dm_touch){(uint32_t)i, (float)fmin(fmax((p.x - x0) / w, 0), 0.999), (float)fmin(fmax((p.y - y0) / h, 0), 0.999)};
    }
    dm_touch_set(t, n);
}
- (BOOL)gameBegin:(UITouch *)t {
    for (int i = 0; i < 16; i++) if (!_game[i]) { _game[i] = t; [_owner setObject:@(C_GAME | (uint64_t)i << 8) forKey:t]; return YES; }
    return NO;
}
- (void)touchesBegan:(NSSet<UITouch *> *)ts withEvent:(UIEvent *)e {
    BOOL game = NO;
    // Gameplay fingers do not prevent a gear tap. A second gear
    // finger blocks it regardless of NSSet order; presentation resets controls.
    for (UITouch *t in ts) {
        CGPoint p = [t locationInView:self];
        if ([self inSettings:p]) { [self beginSettingsTouch:t blocked:NO]; continue; }
        if (_padOff) { game |= [self gameBegin:t]; continue; }
        int hit = [self btnAt:p];
        if (hit >= 0) { [_owner setObject:@(C_BTN | (uint64_t)hit << 8) forKey:t]; continue; }
        // diamond, D-pad, left stick: take the one with the smallest distance / grab radius, if it is <= 1
        CGFloat best = 1; int kind = C_NONE, idx = 0;
        CGFloat f = dist(p, self.faceCenter) / (self.faceGap + self.faceR * 1.6); if (f <= best) { best = f; kind = C_FACE; }
        CGFloat d = dist(p, self.dpadCenter) / (self.dpadR * K_DPAD_GRAB); if (d < best) { best = d; kind = C_DPAD; }
        if (!_stick[0]) { CGFloat s = dist(p, self.stickHome) / ([self stickR:0] * K_STICK_GRAB); if (s < best) { best = s; kind = C_STICK; } }
        if (kind == C_NONE && !_stick[1] && [self inRightArea:p]) { kind = C_STICK; idx = 1; _rCentre = p; }   // the right stick: centred where the touch lands
        if (kind == C_FACE) { [_owner setObject:@(C_FACE) forKey:t]; [_faceOf setObject:@([self faceAt:p]) forKey:t]; }
        else if (kind == C_DPAD) [_owner setObject:@(C_DPAD) forKey:t];
        else if (kind == C_STICK) { [_owner setObject:@(C_STICK | (uint64_t)idx << 8) forKey:t]; _stick[idx] = t; _stickNow[idx] = p; }
        else game |= [self gameBegin:t];
    }
    if (game) [self pushGame];
    [self recompute];
    [self refresh];
}
- (void)touchesMoved:(NSSet<UITouch *> *)ts withEvent:(UIEvent *)e {
    BOOL game = NO;
    for (UITouch *t in ts) {
        uint64_t v = [_owner objectForKey:t].unsignedLongLongValue; int c = (int)(v & 0xff); CGPoint p = [t locationInView:self];
        if (c == C_SETTINGS) {
            if (t == _settingsTouch) [self checkSettingsMovementForTouch:t event:e];
            if (![self inSettings:p]) dm_tc_gear_block(&_settingsGesture);
        } else if (c == C_FACE) [_faceOf setObject:@([self faceAt:p]) forKey:t];
        else if (c == C_STICK) { _stickNow[v >> 8] = p;
            if ((v >> 8) == 1) { CGFloat d = dist(p, _rCentre), R = [self stickR:1];   // the right stick's centre follows a finger past its radius, so turning back responds at once
                if (d > R) _rCentre = CGPointMake(p.x - (p.x - _rCentre.x) * R / d, p.y - (p.y - _rCentre.y) * R / d); } }
        else if (c == C_GAME) game = YES;
    }
    if (game) [self pushGame];
    [self recompute];
    [self refresh];
}
- (void)endTouches:(NSSet<UITouch *> *)ts event:(UIEvent *)event cancelled:(BOOL)cancelled {
    BOOL game = NO, open = NO;
    for (UITouch *t in ts) {
        uint64_t v = [_owner objectForKey:t].unsignedLongLongValue;
        if ((v & 0xff) == C_SETTINGS && t == _settingsTouch) {
            if (!cancelled) {
                [self checkSettingsMovementForTouch:t event:event];
                CGPoint p = [t locationInView:self];
                open = dm_tc_gear_tap(&_settingsGesture, _settingsToken, (dm_tc_point){p.x, p.y}, [self touchLayout].gear);
            }
            dm_tc_gear_cancel(&_settingsGesture); _settingsTouch = nil; _settingsToken = 0;
        }
        if ((v & 0xff) == C_GAME && (v >> 8) < 16) { _game[v >> 8] = nil; game = YES; }
        [_owner removeObjectForKey:t]; [_faceOf removeObjectForKey:t]; for (int i = 0; i < 2; i++) if (t == _stick[i]) _stick[i] = nil;
    }
    if (game) [self pushGame];
    [self recompute];
    [self refresh];
    if (open) [self openSettings];
}
- (void)touchesEnded:(NSSet<UITouch *> *)ts withEvent:(UIEvent *)e { [self endTouches:ts event:e cancelled:NO]; }
- (void)touchesCancelled:(NSSet<UITouch *> *)ts withEvent:(UIEvent *)e { [self endTouches:ts event:e cancelled:YES]; }
- (void)reset {
    dm_tc_gear_cancel(&_settingsGesture); _settingsTouch = nil; _settingsToken = 0;
    [_owner removeAllObjects]; [_faceOf removeAllObjects]; _stick[0] = _stick[1] = nil;
    for (int i = 0; i < 16; i++) _game[i] = nil;
    [self pushGame]; [self recompute]; [self refresh];
}

// ---- Shapes ----
static CGPathRef circlePath(CGPoint c, CGFloat r) { return CGPathCreateWithEllipseInRect(CGRectMake(c.x - r, c.y - r, 2 * r, 2 * r), NULL); }
static CGPathRef dropPath(CGPoint c, CGFloat r, CGFloat tipAngle, CGFloat round) {   // teardrop: circle + two tangents meeting at the tip, tip slightly rounded
    CGFloat d = r * K_DROP_TIP, th = acos(r / d);
    CGPoint tip = CGPointMake(c.x + d * cos(tipAngle), c.y + d * sin(tipAngle));
    CGPoint p1 = CGPointMake(c.x + r * cos(tipAngle + th), c.y + r * sin(tipAngle + th)), p2 = CGPointMake(c.x + r * cos(tipAngle - th), c.y + r * sin(tipAngle - th));
    CGMutablePathRef p = CGPathCreateMutable();
    CGPathMoveToPoint(p, NULL, p2.x, p2.y);
    CGPathAddArcToPoint(p, NULL, tip.x, tip.y, p1.x, p1.y, round);
    CGPathAddArc(p, NULL, c.x, c.y, r, tipAngle + th, tipAngle - th + 2 * M_PI, false);
    CGPathCloseSubpath(p); return p;
}
static CGPathRef armPath(CGPoint c, CGFloat R, CGFloat w, CGFloat in, CGFloat angle, CGFloat round) {   // one D-pad arm: an upward pentagon (tip toward the centre) rotated by angle around the centre
    CGPoint v[5] = {{-w, -R}, {w, -R}, {w, -(in + w)}, {0, -in}, {-w, -(in + w)}};
    CGFloat cs = cos(angle), sn = sin(angle);
    for (int i = 0; i < 5; i++) v[i] = CGPointMake(c.x + v[i].x * cs - v[i].y * sn, c.y + v[i].x * sn + v[i].y * cs);
    CGMutablePathRef p = CGPathCreateMutable();
    CGPathMoveToPoint(p, NULL, (v[4].x + v[0].x) / 2, (v[4].y + v[0].y) / 2);
    for (int i = 0; i < 5; i++) CGPathAddArcToPoint(p, NULL, v[i].x, v[i].y, v[(i + 1) % 5].x, v[(i + 1) % 5].y, round);
    CGPathCloseSubpath(p); return p;
}
static void setPath(CAShapeLayer *l, CGPathRef p) { l.path = p; l.shadowPath = p; CGPathRelease(p); }
static void placeLabel(CATextLayer *t, CGPoint c, CGFloat fs) {
    CTFontRef f = CTFontCreateUIFontForLanguage(kCTFontUIFontEmphasizedSystem, fs, NULL);
    t.font = f; t.fontSize = fs;
    CGFloat h = CTFontGetAscent(f) + CTFontGetDescent(f) + CTFontGetLeading(f), w = fs * 3;
    t.frame = CGRectMake(c.x - w / 2, c.y - h / 2, w, h);
    CFRelease(f);
}

- (void)layoutSubviews {
    [super layoutSubviews];
    if (_layoutValid && (!CGRectEqualToRect(_previousBounds, self.bounds) || !UIEdgeInsetsEqualToEdgeInsets(_previousInsets, self.safeAreaInsets))) [self reset];
    _layoutValid = YES; _previousBounds = self.bounds; _previousInsets = self.safeAreaInsets;
    CGFloat u = self.u;
    [CATransaction begin]; [CATransaction setDisableActions:YES];
    _controls.frame = self.layer.bounds;
    CGFloat scale = self.window.screen.scale;
    if (isfinite(scale) && scale > 0) for (int b = 0; b < B_N; b++) _label[b].contentsScale = scale;
    for (int b = B_A; b <= B_Y; b++) { CGPoint c = [self facePos:b]; setPath(_key[b], circlePath(c, self.faceR)); placeLabel(_label[b], c, 20 * u); }
    for (int i = 0; i < (int)(sizeof k_btns / sizeof *k_btns); i++) { int b = k_btns[i];
        if (isDrop(b)) {
            BOOL right = b == B_ZR || b == B_R; CGPoint c = [self dropCenter:b];
            setPath(_key[b], dropPath(c, [self dropR:b], right ? -M_PI_4 : -3 * M_PI_4, 4 * u)); placeLabel(_label[b], c, 16 * u);   // tip toward the near top corner
        } else if (isClick(b)) {
            CGPoint c = [self clickCenter:b]; setPath(_key[b], circlePath(c, K_CLICK_R * u)); placeLabel(_label[b], c, 13 * u);
        } else {
            CGRect rc = [self pillRect:b];
            setPath(_key[b], CGPathCreateWithRoundedRect(rc, rc.size.height / 2, rc.size.height / 2, NULL)); placeLabel(_label[b], CGPointMake(CGRectGetMidX(rc), CGRectGetMidY(rc)), 18 * u);
        }
    }
    static const struct { int b; CGFloat angle; } arms[] = {{B_UP, 0}, {B_RIGHT, M_PI_2}, {B_DOWN, M_PI}, {B_LEFT, -M_PI_2}};   // the same arm in 90° steps
    for (int i = 0; i < 4; i++) setPath(_key[arms[i].b], armPath(self.dpadCenter, self.dpadR, K_ARM_W * u, K_ARM_IN * u, arms[i].angle, 6 * u));
    _gearIcon.frame = uiRect([self touchLayout].gear);
    _gearAccessibility.accessibilityFrameInContainerSpace = _gearIcon.frame;
    setPath(_ring, circlePath(self.stickHome, [self stickR:0]));
    CGFloat k = K_KNOB_R * u; _knob.bounds = CGRectMake(0, 0, 2 * k, 2 * k);
    setPath(_knob, circlePath(CGPointMake(k, k), k));
    CAShapeLayer *in = (CAShapeLayer *)_knob.sublayers.firstObject; CGPathRef ip = circlePath(CGPointMake(k, k), k * 0.62);
    in.frame = _knob.bounds; in.path = ip; CGPathRelease(ip);
    [CATransaction commit];
    [self refresh];
}
- (void)safeAreaInsetsDidChange { [super safeAreaInsetsDidChange]; [self setNeedsLayout]; }
- (void)refresh {   // pressed state → fill, sticks → knob position
    uint64_t all = _faceBits | _dpadBits | _btnBits;
    [CATransaction begin]; [CATransaction setDisableActions:YES];
    for (int b = 0; b < B_N; b++) { BOOL on = (all >> b) & 1;
        _key[b].fillColor = (on ? k_on : k_idle).CGColor; _label[b].foregroundColor = (on ? k_textOn : k_text).CGColor; }
    _gearIcon.tintColor = (_settingsGesture.tracking && !_settingsGesture.blocked ? k_textOn : [UIColor colorWithWhite:1 alpha:DM_TC_GEAR_ALPHA]);
    CGPoint h = self.stickHome, o = [self knobOffset:0];
    _knob.position = CGPointMake(h.x + o.x, h.y + o.y); _knob.fillColor = (_stick[0] ? k_on : k_idle).CGColor;
    [CATransaction commit];
}

// ---- Physical controllers ----
static int32_t axis(float v) { return (int32_t)(fmaxf(-1.f, fminf(1.f, v)) * 32767); }
// Both checks are needed: a framework callback may already be executing when
// its handler is removed. The host also validates the physical slot epoch.
static void read_pad(unsigned player, GCController *controller, uint64_t epoch, GCExtendedGamepad *g) {
    pthread_mutex_lock(&g_mu);
    BOOL valid = g_pad_active && g_pads[player] == controller && g_pad_epoch[player] == epoch;
    uint64_t prior = g_pad_btn[player];
    pthread_mutex_unlock(&g_mu);
    if (!valid) return;
    uint64_t m = 0;
    #define K(btn, bit) if (btn.isPressed) m |= 1ull << bit
    K(g.buttonB, B_A); K(g.buttonA, B_B); K(g.buttonY, B_X); K(g.buttonX, B_Y);
    K(g.leftShoulder, B_L); K(g.rightShoulder, B_R);
    if (g.leftTrigger.value > ((prior & DM_BTN_ZL) ? 0.08f : 0.14f)) m |= DM_BTN_ZL;
    if (g.rightTrigger.value > ((prior & DM_BTN_ZR) ? 0.08f : 0.14f)) m |= DM_BTN_ZR;
    K(g.buttonMenu, B_PLUS); if (g.buttonOptions) K(g.buttonOptions, B_MINUS);
    if (g.leftThumbstickButton) K(g.leftThumbstickButton, B_LS); if (g.rightThumbstickButton) K(g.rightThumbstickButton, B_RS);
    K(g.dpad.left, B_LEFT); K(g.dpad.up, B_UP); K(g.dpad.right, B_RIGHT); K(g.dpad.down, B_DOWN);
    #undef K
    pthread_mutex_lock(&g_mu);
    valid = g_pad_active && g_pads[player] == controller && g_pad_epoch[player] == epoch;
    if (valid) {
        g_pad_btn[player] = m;
        dm_pad_set_player(player, epoch, m, axis(g.leftThumbstick.xAxis.value), axis(g.leftThumbstick.yAxis.value),
                          axis(g.rightThumbstick.xAxis.value), axis(g.rightThumbstick.yAxis.value));
    }
    pthread_mutex_unlock(&g_mu);
    if (valid) dm_controller_feedback_travel_player(player, controller, g.leftTrigger.value, g.rightTrigger.value);
}
- (void)padsChanged {
    if (!NSThread.isMainThread) { dispatch_async(dispatch_get_main_queue(), ^{ [self padsChanged]; }); return; }
    NSArray<GCController *> *controllers = GCController.controllers;
    unsigned limit = dm_input_max_players();
    // Preserve legacy single-player DualSense preference. Multiplayer keeps each
    // occupied identity; enumeration order and controller type cannot steal it.
    GCController *legacyChoice = nil;
    if (limit == 1) {
        if ([controllers containsObject:g_pads[0]]) legacyChoice = g_pads[0];
        for (GCController *c in controllers) if (c.extendedGamepad) {
            if (!legacyChoice) legacyChoice = c;
            if ([c.extendedGamepad isKindOfClass:GCDualSenseGamepad.class]) { legacyChoice = c; break; }
        }
    }
    for (unsigned player = 0; player < limit; ++player) {
        GCController *controller = g_pads[player];
        if (controller && (![controllers containsObject:controller] || !controller.extendedGamepad || (limit == 1 && controller != legacyChoice))) {
            controller.extendedGamepad.valueChangedHandler = nil;
            pthread_mutex_lock(&g_mu);
            g_pads[player] = nil; g_pad_btn[player] = g_pad_epoch[player] = 0;
            pthread_mutex_unlock(&g_mu);
            dm_pad_connect_player(player, 0); dm_controller_feedback_attach_player(player, nil);
            controller.playerIndex = GCControllerPlayerIndexUnset;
        }
    }
    for (GCController *controller in controllers) {
        if (!controller.extendedGamepad || (limit == 1 && controller != legacyChoice)) continue;
        unsigned found = limit;
        for (unsigned player = 0; player < limit; ++player) if (g_pads[player] == controller) found = player;
        if (found == limit) {
            for (unsigned player = 0; player < limit; ++player) if (!g_pads[player]) { found = player; break; }
            if (found == limit) continue;
            pthread_mutex_lock(&g_mu); g_pads[found] = controller; pthread_mutex_unlock(&g_mu);
        }
        if (!g_pad_active || g_pad_epoch[found]) continue;
        uint64_t epoch = dm_pad_connect_player(found, 1);
        pthread_mutex_lock(&g_mu); g_pad_epoch[found] = epoch; pthread_mutex_unlock(&g_mu);
        dm_controller_feedback_attach_player(found, controller);
        unsigned player = found;
        __weak GCController *weakController = controller;
        controller.extendedGamepad.valueChangedHandler = ^(GCExtendedGamepad *g, GCControllerElement *el) {
            (void)el; GCController *controller = weakController;
            if (controller) read_pad(player, controller, epoch, g);
        };
        read_pad(player, controller, epoch, controller.extendedGamepad);
    }
    // A vacant physical P1 slot can still use the on-screen P1 controls while
    // another physical player remains connected.
    update_pad_indicators();
    self->_padOff = g_pads[0] != nil; self->_controls.hidden = self->_padOff; [self reset];
}
- (void)suspendPads {
    if (!NSThread.isMainThread) { dispatch_async(dispatch_get_main_queue(), ^{ [self suspendPads]; }); return; }
    pthread_mutex_lock(&g_mu); g_pad_active = NO; pthread_mutex_unlock(&g_mu);
    for (unsigned player = 0; player < dm_input_max_players(); ++player) {
        g_pads[player].extendedGamepad.valueChangedHandler = nil;
        pthread_mutex_lock(&g_mu); g_pad_btn[player] = g_pad_epoch[player] = 0; pthread_mutex_unlock(&g_mu);
        dm_pad_connect_player(player, 0);
    }
    dm_pad_release_players(); dm_controller_feedback_focus(0); [self reset];
}
- (void)resumePads {
    if (!NSThread.isMainThread) { dispatch_async(dispatch_get_main_queue(), ^{ [self resumePads]; }); return; }
    pthread_mutex_lock(&g_mu); g_pad_active = YES; pthread_mutex_unlock(&g_mu);
    dm_controller_feedback_focus(1); [self padsChanged];
}
@end

UIView *dm_gamepad_view(CGRect frame) { DmGamepad *v = [[DmGamepad alloc] initWithFrame:frame]; g_view = v; return v; }
// Resize cancels only touch ownership. Physical controller slots and feedback
// focus remain live; dm_gamepad_reset() is the separate lifecycle suspension.
void dm_gamepad_geometry_changed(void) {
    if (NSThread.isMainThread) { [g_view reset]; [g_view setNeedsLayout]; }
    else dispatch_async(dispatch_get_main_queue(), ^{ [g_view reset]; [g_view setNeedsLayout]; });
}
void dm_gamepad_reset(void) {
    if (NSThread.isMainThread) [g_view suspendPads];
    else dispatch_async(dispatch_get_main_queue(), ^{ [g_view suspendPads]; });
}
