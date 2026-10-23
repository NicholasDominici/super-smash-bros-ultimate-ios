// The production source latch keeps camera/HUD/insets attached to the completed
// interval even when a later scene requests new geometry before JPEG delivery.
#include "game_profile.h"
#include "smash_display.h"
#include "smash_ui_scope.h"
#include "smash_camera_policy.h"
#include "smash_projection_policy.h"
#include <assert.h>
#include <stdio.h>
static dm_smash_ui_stats ui;
static unsigned prepare_calls;
void dm_smash_ui_snapshot(dm_smash_ui_stats *out){*out=ui;}
void mtl_present_geometry_changed(void){}
void dm_smash_aspect_prepare_interval(const dm_smash_display_geometry_t *geometry){
    dm_smash_display_geometry_t current;dm_smash_display_active(&current);
    assert(current.generation==geometry->generation);++prepare_calls;
}
int main(void){
    float projection[16]={2.f/1920,0,0,0,0,2.f/1440,0,0,0,0,-.003333333f,0,0,0,0,1},original[16];
    memcpy(original,projection,sizeof original);
    for(unsigned i=0;i<1000;++i){double aspect=i%2?678./466:951./669;
        assert(dm_smash_ui_projection(projection,projection,0,aspect));
        assert(projection[0]==original[0] && projection[5]==(float)(projection[0]*aspect));
    }
    projection[4]=.25f;memcpy(original,projection,sizeof original);
    assert(!dm_smash_ui_projection(projection,projection,0,678./466) && !memcmp(original,projection,sizeof original));
    projection[4]=0;projection[0]=1.7f;projection[5]=2;projection[14]=-1;projection[15]=0;
    assert(dm_smash_ui_projection(projection,projection,1,951./669) && projection[0]==1.7f);
    assert(!dm_smash_display_enabled());assert(dm_smash_display_source_aspect()==DM_GAME_PRESENT_ASPECT);
    dm_smash_display_frame disabled;dm_smash_display_source_snapshot(&disabled);
    assert(!disabled.enabled && disabled.geometry.aspect==DM_GAME_PRESENT_ASPECT);
    assert(dm_smash_display_geometry(678,466,3,0,0,21,0,3));dm_smash_display_enable();
    dm_smash_display_geometry_t a,b;dm_smash_display_active(&a);assert(a.generation==1 && a.insets[2]==21);
    for(unsigned i=0;i<3;++i)assert(dm_smash_world_camera(dm_smash_world_camera_callers[i],0x43,4.f/3,1.f,.1f,100));
    assert(!dm_smash_world_camera(0x14e5fa4,0x43,4.f/3,1,.1f,100));
    assert(!dm_smash_world_camera(0x51aa80,0x43,1,1,.1f,100));
    assert(!dm_smash_world_camera(0x51aa80,0x43,NAN,1,.1f,100));
    assert(!dm_smash_world_camera(0x51aa80,0x42,4.f/3,1,.1f,100));
    assert(!dm_smash_display_geometry(NAN,466,3,0,0,0,0,3));
    assert(!dm_smash_display_geometry(678,466,3,0,0,500,0,3));
    assert(!dm_smash_display_geometry(466,678,3,0,0,0,0,1));
    ui.begins=ui.ends=ui.accepted=1;
    dm_smash_display_note_camera(a.aspect,a.generation);dm_smash_display_note_hud(a.aspect,a.generation,1);dm_smash_display_note_projection(a.generation,1);
    assert(dm_smash_display_geometry(951,669,3,0,0,34,0,3));
    dm_smash_display_frame_boundary();dm_smash_display_frame old;dm_smash_display_source_snapshot(&old);
    assert(old.geometry.generation==1 && old.geometry.insets[2]==21 && old.camera_enabled && old.hud_enabled);
    dm_smash_display_active(&b);assert(b.generation==2 && b.insets[2]==34);
    dm_smash_display_frame_boundary();dm_smash_display_frame no_callback;dm_smash_display_source_snapshot(&no_callback);
    assert(no_callback.geometry.generation==2 && !no_callback.camera_enabled && !no_callback.hud_enabled);
    dm_smash_display_note_camera(b.aspect,b.generation);dm_smash_display_note_hud(b.aspect,b.generation,1);dm_smash_display_note_projection(b.generation,1);
    assert(dm_smash_display_geometry(951,669,2,10,0,34,0,4));
    dm_smash_display_frame_boundary();dm_smash_display_frame completed;dm_smash_display_source_snapshot(&completed);
    assert(completed.geometry.generation==2 && completed.geometry.scale==3 && completed.geometry.insets[0]==0 && completed.camera_enabled && completed.hud_enabled);
    dm_smash_display_active(&b);assert(b.generation==3 && b.scale==2 && b.insets[0]==10 && b.orientation==4);
    assert(old.geometry.generation==1 && old.geometry.width==678 && old.geometry.insets[2]==21);
    assert(prepare_calls==3);
    dm_smash_display_note_camera(b.aspect,b.generation);dm_smash_display_note_hud(b.aspect,b.generation,1);dm_smash_display_note_projection(b.generation,0);
    dm_smash_display_frame_boundary();dm_smash_display_source_snapshot(&completed);assert(completed.camera_enabled && !completed.hud_enabled && completed.projection_failures==1);
    uint64_t native_calls=completed.camera_calls;
    dm_smash_display_note_camera_state(b.aspect,b.generation,1);dm_smash_display_note_projection(b.generation,1);
    dm_smash_display_frame_boundary();dm_smash_display_source_snapshot(&completed);
    assert(completed.camera_enabled && completed.hud_enabled && completed.camera_calls==native_calls);
    // Retirement/cache failure at the SAME geometry invalidates the next
    // source interval; the completed prior source remains immutable.
    dm_smash_display_note_camera_state(b.aspect,b.generation,0);
    dm_smash_display_frame frozen;dm_smash_display_source_snapshot(&frozen);assert(frozen.camera_enabled);
    dm_smash_display_frame_boundary();dm_smash_display_source_snapshot(&completed);
    assert(completed.geometry.generation==b.generation && !completed.camera_enabled && completed.camera_calls==native_calls);
    puts("PASS: production interval latch, delayed source binding, inset/scale/orientation generations, camera policy, invalid geometry and projection failure");
}
