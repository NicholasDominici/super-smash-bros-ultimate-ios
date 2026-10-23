// Camera/HUD share a latched game interval. Source metadata describes the frame
// just recorded, never a later UIKit request or an asynchronous completion time.
#include "dm.h"
#include "smash_display.h"
#include "smash_ui_scope.h"
#include "smash_display_policy.h"
#ifndef DM_GAME_SMASH_LIVE_DISPLAY
#define DM_GAME_SMASH_LIVE_DISPLAY 0
#endif
#include <math.h>
#include <stdatomic.h>
static pthread_mutex_t display_mu=PTHREAD_MUTEX_INITIALIZER;
static dm_smash_display_geometry_t requested,active;
static int requested_valid;
static _Atomic int enabled;
static uint64_t camera_calls,camera_generation,hud_generation;
static uint64_t projection_generation,projection_failures,previous_projection_failures;
static double camera_aspect,hud_aspect;
static int camera_valid;
static _Thread_local dm_smash_display_frame source;
static uint64_t frame_serial;
static dm_smash_ui_stats previous_ui;
static int shipping_baseline=1;
static unsigned shipping_healthy;
static uint64_t shipping_generation;
extern void mtl_present_geometry_changed(void);
// Optional platform frontends provide strong definitions. The default keeps
// ordinary/iOS source builds linkable when the Mac-only development relay is off.
__attribute__((weak)) void dm_smash_relay_start(void){}
__attribute__((weak)) void front_ios_display_geometry_changed(void){}
__attribute__((weak)) void dm_smash_aspect_prepare_interval(const dm_smash_display_geometry_t *geometry){(void)geometry;}
static dm_smash_display_geometry_t fallback(void){
    double aspect=DM_GAME_PRESENT_ASPECT;
    if(!isfinite(aspect) || aspect<=0)aspect=16.0/9.0;
    return (dm_smash_display_geometry_t){.width=1920,.height=1920/aspect,.scale=1,.aspect=DM_GAME_PRESENT_ASPECT,.orientation=3};
}
int dm_smash_display_geometry(double width,double height,double scale,
                              double top,double left,double bottom,double right,int orientation){
    if(!isfinite(width)||!isfinite(height)||!isfinite(scale)||width<=0||height<=0||width>16384||height>16384||scale<=0||scale>8)return 0;
    double values[]={top,left,bottom,right};for(unsigned i=0;i<4;++i)if(!isfinite(values[i])||values[i]<0)return 0;
    double aspect=width/height;if(!isfinite(aspect)||aspect<=1.00001||aspect>4||top+bottom>=height||left+right>=width||
       (orientation!=3 && orientation!=4))return 0;
    pthread_mutex_lock(&display_mu);
    int changed=!requested_valid || requested.width!=width || requested.height!=height || requested.scale!=scale ||
        requested.orientation!=orientation || memcmp(requested.insets,values,sizeof values);
    if(changed){uint64_t generation=requested.generation+1;
        requested=(dm_smash_display_geometry_t){.width=width,.height=height,.scale=scale,.aspect=aspect,.generation=generation,.orientation=orientation};
        memcpy(requested.insets,values,sizeof values);requested_valid=1;
    }
    pthread_mutex_unlock(&display_mu);
    if(changed && atomic_load(&enabled))mtl_present_geometry_changed();
    return 1;
}
void dm_smash_display_enable(void){
    pthread_mutex_lock(&display_mu);active=requested_valid?requested:fallback();
    if(DM_GAME_SMASH_LIVE_DISPLAY){active=dm_smash_display_fit(active,4./3.);active.generation=++shipping_generation;}
    pthread_mutex_unlock(&display_mu);
    atomic_store(&enabled,1);
    dm_smash_relay_start();front_ios_display_geometry_changed();
}
int dm_smash_display_enabled(void){return atomic_load(&enabled);}
double dm_smash_display_scene_aspect(void){
    pthread_mutex_lock(&display_mu);double value=atomic_load(&enabled)?(DM_GAME_SMASH_LIVE_DISPLAY?active.aspect:requested_valid?requested.aspect:DM_GAME_DISPLAY_ASPECT):DM_GAME_DISPLAY_ASPECT;pthread_mutex_unlock(&display_mu);return value;
}
void dm_smash_display_active(dm_smash_display_geometry_t *out){
    if(!out)return;pthread_mutex_lock(&display_mu);*out=atomic_load(&enabled)?active:fallback();pthread_mutex_unlock(&display_mu);
}
void dm_smash_display_note_camera(double aspect,uint64_t generation){
    pthread_mutex_lock(&display_mu);++camera_calls;camera_aspect=aspect;camera_generation=generation;camera_valid=1;pthread_mutex_unlock(&display_mu);
}
void dm_smash_display_note_camera_state(double aspect,uint64_t generation,int admitted){
    pthread_mutex_lock(&display_mu);camera_valid=admitted;
    if(admitted){camera_aspect=aspect;camera_generation=generation;}
    pthread_mutex_unlock(&display_mu);
}
void dm_smash_display_note_hud(double aspect,uint64_t generation,int admitted){
    if(!admitted)return;
    pthread_mutex_lock(&display_mu);hud_aspect=aspect;hud_generation=generation;pthread_mutex_unlock(&display_mu);
}
void dm_smash_display_note_projection(uint64_t generation,int admitted){
    pthread_mutex_lock(&display_mu);if(admitted)projection_generation=generation;else ++projection_failures;pthread_mutex_unlock(&display_mu);
}
void dm_smash_display_frame_boundary(void){
    dm_smash_ui_stats ui;dm_smash_ui_snapshot(&ui);
    pthread_mutex_lock(&display_mu);
    dm_smash_display_geometry_t geometry=atomic_load(&enabled)?active:fallback();
    source=(dm_smash_display_frame){.geometry=geometry,.frame=++frame_serial,.enabled=atomic_load(&enabled),
        .camera_calls=camera_calls,.camera_generation=camera_generation,.hud_generation=hud_generation,
        .camera_aspect=camera_aspect,.hud_aspect=hud_aspect,
        .projection_generation=projection_generation,.projection_failures=projection_failures-previous_projection_failures,
        .ui_accepted=ui.accepted-previous_ui.accepted,.ui_declined=ui.declined-previous_ui.declined,
        .ui_borrowed=ui.borrowed-previous_ui.borrowed,.ui_restored=ui.restored-previous_ui.restored,
        .ui_pose_changes=ui.pose_changes-previous_ui.pose_changes,
        .ui_matrix_calls=ui.matrix_calls-previous_ui.matrix_calls,.ui_matrix_writes=ui.matrix_writes-previous_ui.matrix_writes};
    source.camera_enabled=source.enabled && camera_valid && camera_calls && camera_generation==geometry.generation && fabs(camera_aspect-geometry.aspect)<1.e-5;
    source.hud_enabled=source.enabled && ui.accepted && hud_generation==geometry.generation && fabs(hud_aspect-geometry.aspect)<1.e-5 &&
        projection_generation==geometry.generation && !source.projection_failures &&
        !source.ui_declined && ui.begins==ui.ends;
    previous_ui=ui;
    previous_projection_failures=projection_failures;
    dm_smash_display_geometry_t before=active;
    active=requested_valid?requested:fallback();
    if(DM_GAME_SMASH_LIVE_DISPLAY){
        // First unqualified interval is reported honestly above. Recover the
        // NEXT camera/HUD/presentation pair together; never relabel its raster.
        int healthy=source.camera_enabled && source.hud_enabled && source.ui_accepted;
        if(!healthy){shipping_baseline=1;shipping_healthy=0;}
        else if(shipping_baseline && ++shipping_healthy>=5){shipping_baseline=0;shipping_healthy=0;}
        active=dm_smash_display_fit(active,dm_smash_display_target(active.aspect,shipping_baseline));
        int changed=before.width!=active.width || before.height!=active.height || before.aspect!=active.aspect ||
            before.scale!=active.scale || before.orientation!=active.orientation || memcmp(before.insets,active.insets,sizeof active.insets);
        if(changed)++shipping_generation;
        active.generation=shipping_generation;
    }
    dm_smash_display_geometry_t next=active;
    int presentation_changed=DM_GAME_SMASH_LIVE_DISPLAY && before.generation!=next.generation;
    pthread_mutex_unlock(&display_mu);
    // The just-recorded source is frozen above. Prepare cached native camera
    // data for the NEXT interval, outside the display mutex and GPU queues.
    if(atomic_load(&enabled))dm_smash_aspect_prepare_interval(&next);
    if(presentation_changed){mtl_present_geometry_changed();front_ios_display_geometry_changed();}
}
double dm_smash_display_source_aspect(void){return source.enabled && source.geometry.aspect>0?source.geometry.aspect:DM_GAME_PRESENT_ASPECT;}
uint64_t dm_smash_display_source_generation(void){return source.geometry.generation;}
void dm_smash_display_source_snapshot(dm_smash_display_frame *out){
    if(out){*out=source;if(!out->geometry.aspect)out->geometry=fallback();}
}
