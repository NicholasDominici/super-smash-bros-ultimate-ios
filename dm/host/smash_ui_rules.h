// Metadata-only rule ABI. Exact receiving resources generate the private arrays
// outside this repository; public builds without them retain prepared geometry.
#pragma once
#include <stddef.h>
#include <stdint.h>
typedef struct {
    const char *name,*parent,*parts;
    uint32_t kind;
    float offset_x,offset_y;
    uint8_t grow_x,grow_y,visit_parts;
    int8_t edge_y;
} dm_smash_ui_rule;
typedef struct {
    const char *name,*resource,*root_name;
    float width,height;
    const dm_smash_ui_rule *panes;
    size_t pane_count;
    uint8_t primary;
} dm_smash_ui_layout_rule;
