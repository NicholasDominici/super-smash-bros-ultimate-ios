// Execute the shipping interval policy with synthetic owner evidence. No game,
// device, renderer or cloud backend is involved.
#include "../dm.h"
#undef DM_GAME_SMASH_LIVE_DISPLAY
#define DM_GAME_SMASH_LIVE_DISPLAY 1
#include "../hle_smash_display.c"
#include <assert.h>
static dm_smash_ui_stats fixture_ui;
void dm_smash_ui_snapshot(dm_smash_ui_stats *out){*out=fixture_ui;}
void mtl_present_geometry_changed(void){}
static void healthy(void){
    dm_smash_display_geometry_t g;dm_smash_display_active(&g);
    dm_smash_display_note_camera(g.aspect,g.generation);dm_smash_display_note_camera_state(g.aspect,g.generation,1);
    dm_smash_display_note_hud(g.aspect,g.generation,1);dm_smash_display_note_projection(g.generation,1);
    ++fixture_ui.begins;++fixture_ui.ends;++fixture_ui.accepted;
}
int main(void){
    assert(dm_smash_display_geometry(678,466,3,0,0,34,84,4));dm_smash_display_enable();
    dm_smash_display_geometry_t g;dm_smash_display_active(&g);assert(fabs(g.aspect-4./3)<1.e-9);
    for(unsigned i=0;i<5;++i){healthy();dm_smash_display_frame_boundary();}
    dm_smash_display_active(&g);assert(fabs(g.aspect-678./466)<1.e-9 && g.insets[3]==84);
    uint64_t full_generation=g.generation;healthy();dm_smash_display_frame_boundary();
    dm_smash_display_frame source;dm_smash_display_source_snapshot(&source);assert(source.geometry.generation==full_generation && source.camera_enabled && source.hud_enabled);
    // An unknown owner invalidates the current source honestly, then the next
    // camera/UI interval returns together to the prepared4:3 pair.
    ++fixture_ui.begins;++fixture_ui.ends;++fixture_ui.declined;dm_smash_display_frame_boundary();
    dm_smash_display_source_snapshot(&source);assert(source.geometry.generation==full_generation && !source.hud_enabled);
    dm_smash_display_active(&g);assert(fabs(g.aspect-4./3)<1.e-9 && g.generation>full_generation);
    for(unsigned i=0;i<5;++i){healthy();dm_smash_display_frame_boundary();}dm_smash_display_active(&g);assert(fabs(g.aspect-678./466)<1.e-9);
    // Wide phones retain a coherent proportional4:3 preparation in this
    // variant. The separate16:9 preparation never enables this policy.
    assert(dm_smash_display_geometry(956,440,3,0,44,34,44,3));healthy();dm_smash_display_frame_boundary();
    dm_smash_display_active(&g);assert(fabs(g.aspect-4./3)<1.e-9 && fabs(g.width/g.height-4./3)<1.e-9 && g.insets[1]==0 && g.insets[3]==0);
    puts("PASS shipping display: initialbaseline, narrowqualification, delayed immutable source, unknown-owner recovery, wide coherent fallback and safe-area projection");
}
