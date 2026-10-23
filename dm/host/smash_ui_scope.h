// Method-scoped UI output correction; no pane pointers survive native return.
#pragma once
#include "smash_ui_rules.h"
#include <stdint.h>
typedef int (*dm_smash_ui_read)(uint64_t,void *,size_t);
typedef void (*dm_smash_ui_prepare)(void *,size_t);
typedef void (*dm_smash_ui_local)(void *,void *);
typedef struct {
    uint64_t begins,ends,accepted,declined,borrowed,restored,nested,max_depth,waits;
    uint64_t pose_changes;
    uint64_t matrix_calls,matrix_writes;
    uint64_t overlaps;
} dm_smash_ui_stats;
void dm_smash_ui_setup(uint64_t base,dm_smash_ui_read read,dm_smash_ui_prepare prepare,
                       dm_smash_ui_local local,const dm_smash_ui_layout_rule *rules,size_t count);
int dm_smash_ui_begin(uint64_t layout,uint64_t di,uint64_t context,uint64_t frame,
                      int primary,double aspect,double safe_top,double safe_bottom,double safe_left,double safe_right,int apply);
void dm_smash_ui_end(uint64_t layout,uint64_t di,uint64_t frame);
void dm_smash_ui_after_matrix(uint64_t pane,uint64_t context);
void dm_smash_ui_snapshot(dm_smash_ui_stats *out);
