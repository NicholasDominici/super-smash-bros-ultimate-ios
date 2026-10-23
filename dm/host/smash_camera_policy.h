// Exact receiving final world-camera update callers. Constructor observations
// are diagnostic only; custom square/auxiliary cameras retain game semantics.
#pragma once
#include <math.h>
#include <stdint.h>
static const uint32_t dm_smash_world_camera_callers[]={0x51aa80,0x51aa8c,0x154543c};
static inline int dm_smash_camera_fields(uint16_t flags,float aspect,float fov,float near,float far){
    return flags==0x43 && isfinite(aspect) && aspect>1.00001f && aspect<=4 &&
        isfinite(fov) && fov>0 && fov<3.14159f && isfinite(near) && isfinite(far) && near>0 && far>near;
}
static inline int dm_smash_world_camera(uint64_t caller,uint16_t flags,float aspect,float fov,float near,float far){
    int known=0;for(unsigned i=0;i<sizeof dm_smash_world_camera_callers/sizeof *dm_smash_world_camera_callers;++i)
        known|=caller==dm_smash_world_camera_callers[i];
    return known && dm_smash_camera_fields(flags,aspect,fov,near,far);
}
