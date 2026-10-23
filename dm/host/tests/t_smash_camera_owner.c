// Exercise current-owner resolution and retirement without game files. The
// private native fixture separately calls the exact receiving camera routine.
#include "smash_camera_owner.h"
#include <assert.h>
#include <stdio.h>
static struct {uint64_t slot,holder;unsigned char root[0x1000],replacement[0x1000];} data;
static unsigned writes,updates;
static int deny_tail;
static int read_data(uint64_t at,void *out,size_t n){uint64_t base=(uintptr_t)&data,tail=(uintptr_t)data.root+0xca0+0x144;if(at<base || n>sizeof data || at-base>sizeof data-n)return 0;if(deny_tail && at<tail+0x4c && at+n>tail)return 0;memcpy(out,(void *)(uintptr_t)at,n);return 1;}
static void prepare(void *at,size_t n){unsigned char copy[0x144];assert(n<=sizeof copy && read_data((uintptr_t)at,copy,n));++writes;}
static void scalar(void *p,size_t offset,float v){memcpy((char *)p+offset,&v,4);}
static void update(void *p){float v=tanf(dm_smash_camera_float(p,0x124)*.5f),h=v*dm_smash_camera_float(p,0x128);scalar(p,0x138,v);scalar(p,0x134,h);scalar(p,0x13c,hypotf(1,h));scalar(p,0x140,hypotf(1,v));++updates;}
int main(void){
    data.slot=(uintptr_t)&data.holder;data.holder=(uintptr_t)data.root;unsigned char *camera=data.root+0xca0;
    scalar(camera,0x110,2);scalar(camera,0x118,100000);scalar(camera,0x124,1);scalar(camera,0x128,4.f/3);uint16_t flags=0x43;memcpy(camera+0x12c,&flags,2);update(camera);
    for(unsigned i=0;i<120;++i){double a=i%2?678./466:951./669;assert(dm_smash_camera_prepare_owner((uintptr_t)&data.slot,read_data,prepare,update,a));assert(dm_smash_camera_float(camera,0x128)==(float)a);}
    unsigned count=updates;assert(dm_smash_camera_prepare_owner((uintptr_t)&data.slot,read_data,prepare,update,678./466) && updates==count);
    deny_tail=1;unsigned old_writes=writes;assert(!dm_smash_camera_prepare_owner((uintptr_t)&data.slot,read_data,prepare,update,951./669) && writes==old_writes && updates==count);deny_tail=0;
    memcpy(data.replacement,data.root,sizeof data.root);unsigned char old[0x144];memcpy(old,camera,sizeof old);data.holder=(uintptr_t)data.replacement;
    assert(dm_smash_camera_prepare_owner((uintptr_t)&data.slot,read_data,prepare,update,951./669));assert(!memcmp(old,camera,sizeof old));
    data.holder=0;count=writes;assert(!dm_smash_camera_prepare_owner((uintptr_t)&data.slot,read_data,prepare,update,678./466) && writes==count);
    data.holder=(uintptr_t)data.root;flags=0x42;memcpy(camera+0x12c,&flags,2);assert(!dm_smash_camera_prepare_owner((uintptr_t)&data.slot,read_data,prepare,update,678./466) && writes==count);
    flags=0x43;memcpy(camera+0x12c,&flags,2);scalar(camera,0x128,1);assert(!dm_smash_camera_prepare_owner((uintptr_t)&data.slot,read_data,prepare,update,678./466) && writes==count);
    puts("PASS: current embedded world camera, actual cache validation, repeated folds, unchanged-aspect validation, owner replacement/retirement and native-only wrong flags/custom square");
}
