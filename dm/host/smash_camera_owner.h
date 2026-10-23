// Exact receiving world owner: the game obtains the current root through two
// indirections, then its embedded primary camera at+ca0. Resolve every interval;
// no camera/root pointer is retained across the guest's frame or scene lifetime.
#pragma once
#include "smash_camera_policy.h"
#include <stddef.h>
#include <string.h>
typedef int (*dm_smash_camera_read)(uint64_t,void *,size_t);
typedef void (*dm_smash_camera_prepare)(void *,size_t);
typedef void (*dm_smash_camera_update)(void *);
static inline float dm_smash_camera_float(const unsigned char *p,size_t offset){float v;memcpy(&v,p+offset,4);return v;}
static inline int dm_smash_camera_prepare_owner(uint64_t slot,dm_smash_camera_read read,
        dm_smash_camera_prepare prepare,dm_smash_camera_update update,double aspect){
    if(!isfinite(aspect) || aspect<=1.00001 || aspect>4)return 0;
    uint64_t holder=0,root=0;
    if(!read(slot,&holder,8) || !holder || !read(holder,&root,8) || !root || root>UINT64_MAX-0xe30)return 0;
    // Native Update also reads its optional plane at+160 and flag at+180.
    // The receiving adjacent-camera spacing establishes the full190-byte object.
    uint64_t pointer=root+0xca0;unsigned char camera[0x190];
    if(!read(pointer,camera,sizeof camera))return 0;
    uint16_t flags;memcpy(&flags,camera+0x12c,2);
    if(!dm_smash_camera_fields(flags,dm_smash_camera_float(camera,0x128),dm_smash_camera_float(camera,0x124),
                              dm_smash_camera_float(camera,0x110),dm_smash_camera_float(camera,0x118)))return 0;
    for(unsigned i=0x80;i<0x100;i+=4)if(!isfinite(dm_smash_camera_float(camera,i)))return 0;
    float target=(float)aspect;
    if(dm_smash_camera_float(camera,0x128)!=target){
        prepare((void *)(uintptr_t)pointer,0x144);
        memcpy((void *)(uintptr_t)(pointer+0x128),&target,4);
        // Use the exact receiving native routine, including its derived frustum
        // coefficients. Updating the aspect scalar alone leaves stale caches.
        update((void *)(uintptr_t)pointer);
    }
    if(!read(pointer,camera,sizeof camera))return 0;
    float fov=dm_smash_camera_float(camera,0x124),horizontal=dm_smash_camera_float(camera,0x134),vertical=dm_smash_camera_float(camera,0x138);
    float inverse_h=dm_smash_camera_float(camera,0x13c),inverse_v=dm_smash_camera_float(camera,0x140);
    if(dm_smash_camera_float(camera,0x128)!=target || !isfinite(horizontal) || !isfinite(vertical) || vertical<=0 ||
       fabsf(horizontal/vertical-target)>1.e-3f || fabsf(vertical-tanf(fov*.5f))>1.e-3f ||
       !isfinite(inverse_h) || !isfinite(inverse_v) ||
       fabsf(inverse_h-hypotf(1,horizontal))>1.e-3f*(1+fabsf(inverse_h)) ||
       fabsf(inverse_v-hypotf(1,vertical))>1.e-3f*(1+fabsf(inverse_v)))return 0;
    return 1;
}
