// One requested scene snapshot, one active guest interval, one immutable raster
// snapshot. The renderer must carry source metadata through its native queues.
#pragma once
#include <stdint.h>
typedef struct {
    double width,height,scale,aspect,insets[4];
    uint64_t generation;
    int orientation;
} dm_smash_display_geometry_t;
typedef struct {
    dm_smash_display_geometry_t geometry;
    uint64_t frame,camera_calls,camera_generation,hud_generation;
    uint64_t ui_accepted,ui_declined,ui_borrowed,ui_restored,ui_pose_changes;
    uint64_t ui_matrix_calls,ui_matrix_writes,projection_generation,projection_failures;
    double camera_aspect,hud_aspect;
    int enabled,camera_enabled,hud_enabled;
} dm_smash_display_frame;
int dm_smash_display_geometry(double width,double height,double scale,
                              double top,double left,double bottom,double right,int orientation);
void dm_smash_display_enable(void);
int dm_smash_display_enabled(void);
double dm_smash_display_scene_aspect(void);
void dm_smash_display_active(dm_smash_display_geometry_t *out);
void dm_smash_display_note_camera(double aspect,uint64_t generation);
// Fresh owner-state validation is separate from native observer call activity.
void dm_smash_display_note_camera_state(double aspect,uint64_t generation,int admitted);
void dm_smash_display_note_hud(double aspect,uint64_t generation,int admitted);
void dm_smash_display_note_projection(uint64_t generation,int admitted);
void dm_smash_display_frame_boundary(void);
double dm_smash_display_source_aspect(void);
uint64_t dm_smash_display_source_generation(void);
void dm_smash_display_source_snapshot(dm_smash_display_frame *out);
