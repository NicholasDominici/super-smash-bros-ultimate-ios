// Synthetic owners, matrices and sparse main facts exercise the real adapter.
// No game resource or executable fixture is included; no device claims follow.
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "game_profile.h"
#undef DM_GAME_PROGRAM_ID
#define DM_GAME_PROGRAM_ID 0x01006a800016e000ull
#undef DM_GAME_PRESENT_ASPECT
#define DM_GAME_PRESENT_ASPECT (4.0/3.0)
#include "dm.h"
static unsigned fatal_calls;
#undef die
#define die(...) do { ++fatal_calls; return; } while (0)
#include "../hle_smash_aspect.c"

module_t g_mod[MAX_MOD];int g_nmod;
static void (*callbacks[OBS_MAX])(const uint64_t *);
static int missing;
static unsigned write_calls;
static struct { uint8_t owner[0x660],layout[0x100]; } fixture;
void gate_obs_set(int id,void(*fn)(const uint64_t *)){assert(id>0&&id<OBS_MAX);callbacks[id]=fn;}
int gate_obs_present(int id){return id!=missing;}
int dm_guest_copy_mapped(uint64_t a,void *out,size_t n){
    uintptr_t b=(uintptr_t)&fixture;
    if(a<b || n>sizeof fixture || a-b>sizeof fixture-n)return 0;
    memcpy(out,(const void *)(uintptr_t)a,n);return 1;
}
void dm_guest_write_prepare(void *a,size_t n){assert(a&&n);++write_calls;}
static void put32(void *p,unsigned o,uint32_t w){memcpy((uint8_t *)p+o,&w,4);}
static void put64(void *p,unsigned o,uint64_t w){memcpy((uint8_t *)p+o,&w,8);}
static void putfloat(void *p,unsigned o,float w){memcpy((uint8_t *)p+o,&w,4);}
static uint32_t get32(void *p,unsigned o){uint32_t w;memcpy(&w,(uint8_t *)p+o,4);return w;}
static float getfloat(void *p,unsigned o){float f;memcpy(&f,(uint8_t *)p+o,4);return f;}
static void wire(unsigned perspective){
    memset(&fixture,0,sizeof fixture);
    put64(fixture.owner,0x50,(uintptr_t)g_mod[0].base+0x523e840);
    put64(fixture.owner,0x458,(uintptr_t)fixture.layout);
    putfloat(fixture.layout,0x28,1920);putfloat(fixture.layout,0x2c,1440);
    fixture.owner[0x654]=(uint8_t)perspective;
}
static void frame(uint8_t *storage,int perspective){
    memset(storage,0,1024);uint64_t *r=(uint64_t *)(void *)storage;
    r[0]=(uintptr_t)fixture.owner+0x50;r[1]=(uintptr_t)storage+864;
    r[30]=0x12345678;put64(storage,808,(uintptr_t)g_mod[0].base+0x3775a24);
    float m[16]={0};m[0]=perspective?1.5f:2.f/1920.f;m[5]=perspective?2.f:2.f/1440.f;
    m[10]=-1;m[11]=perspective?-.1f:0;m[14]=perspective?-1:0;m[15]=perspective?0:1;
    memcpy(storage+864,m,sizeof m);
}
int main(void){
    g_nmod=1;g_mod[0].size=0x5940000;g_mod[0].base=calloc(1,g_mod[0].size);assert(g_mod[0].base);
    strcpy(g_mod[0].name,"main");strcpy(g_mod[0].build_id,"wrong");
    dm_smash_aspect_install();assert(!atomic_load(&aspect_installed));
    strcpy(g_mod[0].build_id,aspect_build);
    put32(g_mod[0].base,0x4f08bc,0x52955568);
    put32(g_mod[0].base,0x4f08c0,0x72a7f548);
    put32(g_mod[0].base,0x4f09ac,0x52955576);
    put32(g_mod[0].base,0x4f09b0,0x72a7f556);
    put32(g_mod[0].base,0x4fe3bc,0x52955568);
    put32(g_mod[0].base,0x4fe3c0,0x72a7f548);
    put32(g_mod[0].base,0x5050ec,0x52955568);
    put32(g_mod[0].base,0x5050f0,0x72a7f548);
    put32(g_mod[0].base,0x5145cc,0x52955569);
    put32(g_mod[0].base,0x5145d0,0x72a7f549);
    put32(g_mod[0].base,0x51465c,0x52955569);
    put32(g_mod[0].base,0x514660,0x72a7f549);
    put32(g_mod[0].base,0x147f0e0,0x52955568);
    put32(g_mod[0].base,0x147f0e4,0x72a7f548);
    put32(g_mod[0].base,0x1493090,0x52955568);
    put32(g_mod[0].base,0x1493094,0x72a7f548);
    put32(g_mod[0].base,0x14e5efc,0x52955569);
    put32(g_mod[0].base,0x14e5f00,0x72a7f549);
    put32(g_mod[0].base,0x14e6014,0xf2d55576);
    put32(g_mod[0].base,0x14e6018,0xf2e7f556);
    put32(g_mod[0].base,0x14e64d4,0x52955568);
    put32(g_mod[0].base,0x14e64d8,0x72a7f548);
    put32(g_mod[0].base,0x29fabfc,0x5295556f);
    put32(g_mod[0].base,0x29fac00,0x72a7f54f);
    put32(g_mod[0].base,0x3158624,0x52955575);
    put32(g_mod[0].base,0x3158628,0x72a7f555);
    put32(g_mod[0].base,0x354e2bc,0xd295556c);
    put32(g_mod[0].base,0x354e2c0,0xf2a7f54c);
    put32(g_mod[0].base,0x361d3a4,0x52955568);
    put32(g_mod[0].base,0x361d3a8,0x72a7f548);
    put32(g_mod[0].base,0x4472c5c,0x3faaaaab);
    put32(g_mod[0].base,0x44689f4,0x3ab60b61);
    put32(g_mod[0].base,0x374e114,0x52816c29);
    put32(g_mod[0].base,0x374e118,0x72a756c9);
    put32(g_mod[0].base,0x44d64,0xf9400c29);
    put32(g_mod[0].base,0x378f144,0xa9014ff4);
    put32(g_mod[0].base,0x3775a1c,0x9100c3e1);
    put32(g_mod[0].base,0x3775a20,0x97233cd0);
    put32(g_mod[0].base,0x3743e60,0xd2d1c728);
    put32(g_mod[0].base,0x3743e64,0xf2e7fc68);
    put32(g_mod[0].base,0x37c9a5c,0xb2610fe1);
    put32(g_mod[0].base,0x37c9a9c,0xb2610fe9);
    put32(g_mod[0].base,0x37c9c50,0xb2610fe9);
    put32(g_mod[0].base,0x37ca3cc,0xb2610fe8);
    put32(g_mod[0].base,0x37caf68,0xb2610fe9);
    put32(g_mod[0].base,0x37c9a6c,0xb27c7be9);
    put32(g_mod[0].base,0x37c9a78,0xf2c000eb);
    put32(g_mod[0].base,0x37c9b9c,0x72a000e1);
    put32(g_mod[0].base,0x37c9a70,0xd2afe40b);
    put32(g_mod[0].base,0x37c9a74,0xf2afe409);
    put32(g_mod[0].base,0x37c9b98,0x528fe401);
    missing=OBS_SMASH_UI_DRAW;dm_smash_aspect_install();assert(!atomic_load(&aspect_installed));
    assert(fatal_calls==2);
    missing=0;put32(g_mod[0].base,0x4472c5c,0x3fe38e39);
    dm_smash_aspect_install();assert(!atomic_load(&aspect_installed));
    assert(fatal_calls==3);
    put32(g_mod[0].base,0x4472c5c,0x3faaaaab);dm_smash_aspect_install();assert(atomic_load(&aspect_installed));
    assert(callbacks[OBS_SMASH_UI_PROJECTION]&&callbacks[OBS_SMASH_UI_DRAW]);
    _Alignas(16) uint8_t storage[1024];uint64_t *r=(uint64_t *)(void *)storage;uint8_t saved[248];
    wire(1);frame(storage,1);memcpy(saved,storage,sizeof saved);
    callbacks[OBS_SMASH_UI_PROJECTION](r);
    assert(getfloat(storage,864)==1.125f&&getfloat(storage,884)==1.5f);
    assert(!memcmp(saved,storage,sizeof saved));assert(write_calls==1);
    wire(0);frame(storage,0);float old[16];memcpy(old,storage+864,sizeof old);
    callbacks[OBS_SMASH_UI_PROJECTION](r);assert(!memcmp(old,storage+864,sizeof old));
    // Gate LR differs from original caller LR; only the explicit saved caller
    // slot admits a call, and unrelated SDK callers never change their data.
    wire(1);frame(storage,1);put64(storage,808,0x1234);memcpy(old,storage+864,sizeof old);
    callbacks[OBS_SMASH_UI_PROJECTION](r);assert(!memcmp(old,storage+864,sizeof old));
    frame(storage,1);r[1]+=4;callbacks[OBS_SMASH_UI_PROJECTION](r);assert(write_calls==1);
    frame(storage,1);putfloat(fixture.layout,0x2c,1080);callbacks[OBS_SMASH_UI_PROJECTION](r);assert(write_calls==1);
    wire(2);frame(storage,1);callbacks[OBS_SMASH_UI_PROJECTION](r);assert(write_calls==1);
    wire(1);frame(storage,1);putfloat(storage,864,NAN);callbacks[OBS_SMASH_UI_PROJECTION](r);assert(write_calls==1);
    wire(0);frame(storage,0);put32(g_mod[0].base,0x523d480,1920);put32(g_mod[0].base,0x523d484,1080);
    for(unsigned pass=0;pass<=6;++pass){
        r[2]=pass;unsigned before=write_calls;callbacks[OBS_SMASH_UI_DRAW](r);assert(write_calls==before+3);
        assert(get32(fixture.owner,0x50+0xe0)==1920&&get32(fixture.owner,0x50+0xe4)==1440);
        int32_t expected[4];assert(aspect_rect(1920,1080,pass,expected));
        for(unsigned i=0;i<4;++i){
            assert((int32_t)get32(fixture.owner,0x50+0x130+4*i)==expected[i]);
            assert(getfloat(fixture.owner,0x50+0x100+4*i)==(float)expected[i]);
        }
    }
    int32_t rect[4];assert(aspect_rect(1920,1080,4,rect));
    assert(rect[0]==1024&&rect[1]==272&&rect[2]==832&&rect[3]==535);
    assert(aspect_rect(1601,901,1,rect));assert(rect[0]==0&&rect[1]==197&&rect[2]==800&&rect[3]==506);
    assert(!aspect_rect(0,1080,0,rect)&&!aspect_rect(1920,1080,7,rect)&&!aspect_rect(100,100,3,rect));
    unsigned before=write_calls;r[2]=7;callbacks[OBS_SMASH_UI_DRAW](r);assert(write_calls==before);
    r[2]=0;put32(g_mod[0].base,0x523d480,0);callbacks[OBS_SMASH_UI_DRAW](r);assert(write_calls==before);
    g_mod[0].base[0x593b8d4]=1;callbacks[OBS_SMASH_UI_DRAW](r);assert(write_calls==before+3);
    dm_smash_aspect_stats st;dm_smash_aspect_get_stats(&st);
    assert(st.installed&&st.projections==2&&st.perspective_projections==1&&st.draws==8&&st.rejected>=5);
    free(g_mod[0].base);puts("PASS: exact-build Smash4:3 projection, caller/frame admission and seven pass clipping contracts");return 0;
}
