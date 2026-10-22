// Title/build-scoped UI data corrections before the original SDK copy/draw.
// No executable writes, saved-register changes, generic NVN interception,
// physical raster resizing or simulation timing changes occur here.
#include "dm.h"
#include "smash_aspect.h"
#include <math.h>
#include <stdatomic.h>

static module_t *aspect_main;
static _Atomic int aspect_installed;
static _Atomic uint64_t projection_count, perspective_count, draw_count, reject_count;
static const char aspect_build[] = "21450c647b8c5940ed5b68218ea128fd";

static int aspect_read(uint64_t address, void *out, size_t length) {
    if (!address || !out || !length) return 0;
    uint64_t base = aspect_main ? (uint64_t)(uintptr_t)aspect_main->base : 0;
    if (aspect_main && address >= base && length <= aspect_main->size &&
        address-base <= aspect_main->size-length) {
        memcpy(out, (const void *)(uintptr_t)address, length); return 1;
    }
    return dm_guest_copy_mapped(address, out, length);
}
static uint64_t aspect_base(void) { return (uint64_t)(uintptr_t)aspect_main->base; }
static int near_value(float value, float expected) {
    return isfinite(value) && fabsf(value-expected) <= fmaxf(1.e-8f, fabsf(expected)*1.e-5f);
}
static int aspect_owner(uint64_t di, unsigned *perspective) {
    if (di < 0x50 || di > UINT64_MAX-0x610) return 0;
    uint8_t owner[0x660];
    if (!aspect_read(di-0x50, owner, sizeof owner)) return 0;
    uint64_t table=0, layout=0; float dimensions[2];
    memcpy(&table, owner+0x50, sizeof table);
    memcpy(&layout, owner+0x458, sizeof layout);
    if (table != aspect_base()+0x523e840 || !layout || layout > UINT64_MAX-0x30 ||
        !aspect_read(layout+0x28, dimensions, sizeof dimensions)) return 0;
    // The preparation resizes exactly the362 engine-primary layouts. Reusable
    // parts keep authored headers and are not independently admitted here.
    int admitted=(dimensions[0]==1920.f && dimensions[1]==1440.f) ||
                 (dimensions[0]==1280.f && dimensions[1]==960.f);
    if (!admitted || owner[0x654]>1) return 0;
    *perspective=owner[0x654]; return 1;
}
static void aspect_reject(void) { atomic_fetch_add_explicit(&reject_count,1,memory_order_relaxed); }

static void aspect_projection(const uint64_t *regs) {
    if (!atomic_load_explicit(&aspect_installed,memory_order_acquire)) return;
    // site_obs saves original x29/x30, then _dm_gate opens its800-byte frame.
    // regs[30] is the gate return PC. The original callee LR is the next
    // frame's saved x30 at+808. The admitted call passes X1=callerSP+0x30,
    // hence the temporary matrix is exactly regs+864. Both are ABI gates.
    uint64_t caller=0; memcpy(&caller,(const uint8_t *)regs+808,sizeof caller);
    if (caller != aspect_base()+0x3775a24 ||
        regs[1] != (uint64_t)(uintptr_t)((const uint8_t *)regs+864)) return;
    unsigned perspective=0;
    if (!aspect_owner(regs[0],&perspective)) { aspect_reject(); return; }
    float matrix[16]; memcpy(matrix,(const void *)(uintptr_t)regs[1],sizeof matrix);
    for (unsigned i=0;i<16;++i) if (!isfinite(matrix[i])) { aspect_reject(); return; }
    if (perspective) {
        // Shared4:3 already makes X4/3 larger. Scaling both axes by3/4
        // restores authored horizontal extent and adds vertical field.
        if (!(matrix[0]>0 && matrix[5]>0) || !near_value(matrix[0]/matrix[5],.75f) ||
            matrix[15]!=0.f || matrix[14]!=-1.f) { aspect_reject(); return; }
        matrix[0]*=.75f; matrix[5]*=.75f;
        dm_guest_write_prepare((void *)(uintptr_t)regs[1],sizeof matrix);
        memcpy((void *)(uintptr_t)regs[1],matrix,sizeof matrix);
        atomic_fetch_add_explicit(&perspective_count,1,memory_order_relaxed);
    } else {
        // Default orthographic rows were prepared offline; the two custom
        // layout_rect screens derive these same rows from resized canvases.
        if (!near_value(matrix[0],2.f/1920.f) || !near_value(matrix[5],2.f/1440.f)) {
            aspect_reject(); return;
        }
    }
    atomic_fetch_add_explicit(&projection_count,1,memory_order_relaxed);
}

static int aspect_rect(int width,int height,unsigned pass,int32_t rect[4]) {
    if (width<1 || height<1 || width>16384 || height>16384 || pass>6) return 0;
    int x=0,y=0,w=width,h=height;
    if (pass>=1 && pass<=4) {
        w=width/2; h=(height*9)/16; y=(height-h)/2;
        if (pass==2 || pass==4) x=width/2;
        if (pass==3 || pass==4) { x+=64; y+=36; w-=128; h-=72; }
    } else if (pass>=5) { w=width/2; if(pass==6)x=width/2; }
    if(w<1 || h<1) return 0;
    rect[0]=x;rect[1]=y;rect[2]=w;rect[3]=h;return 1;
}
static void aspect_draw(const uint64_t *regs) {
    if (!atomic_load_explicit(&aspect_installed,memory_order_acquire)) return;
    unsigned perspective=0;
    if (!aspect_owner(regs[0],&perspective)) { aspect_reject(); return; }
    (void)perspective;
    int32_t config[2],rect[4]; uint8_t override=0;
    if (!aspect_read(aspect_base()+0x523d480,config,sizeof config) ||
        !aspect_read(aspect_base()+0x593b8d4,&override,sizeof override)) { aspect_reject(); return; }
    if(override) { config[0]=1920;config[1]=1080; }
    if (!aspect_rect(config[0],config[1],(unsigned)regs[2],rect)) { aspect_reject(); return; }
    const int32_t logical[2]={1920,1440};
    const float viewport[6]={(float)rect[0],(float)rect[1],(float)rect[2],(float)rect[3],0.f,1.f};
    uint8_t *di=(uint8_t *)(uintptr_t)regs[0];
    dm_guest_write_prepare(di+0xe0,sizeof logical);
    dm_guest_write_prepare(di+0x100,sizeof viewport);
    dm_guest_write_prepare(di+0x130,sizeof rect);
    memcpy(di+0xe0,logical,sizeof logical);
    memcpy(di+0x100,viewport,sizeof viewport);
    memcpy(di+0x130,rect,sizeof rect);
    // The original method now sets the identical physical pass rectangle;
    // SDK nested/capture paths save and restore these coherent base fields.
    atomic_fetch_add_explicit(&draw_count,1,memory_order_relaxed);
}

void dm_smash_aspect_get_stats(dm_smash_aspect_stats *out) {
    if(!out)return;
    *out=(dm_smash_aspect_stats){.projections=atomic_load(&projection_count),
        .perspective_projections=atomic_load(&perspective_count),.draws=atomic_load(&draw_count),
        .rejected=atomic_load(&reject_count),.installed=atomic_load(&aspect_installed)};
}

void dm_smash_aspect_install(void) {
    if(DM_GAME_PROGRAM_ID!=0x01006a800016e000ull ||
       fabs(DM_GAME_PRESENT_ASPECT-4.0/3.0)>1.e-9 || atomic_load(&aspect_installed))return;
    module_t *candidate=NULL;
    for(int i=0;i<g_nmod;++i)if(!strcmp(g_mod[i].name,"main"))candidate=&g_mod[i];
    if(!candidate || !candidate->base || strcmp(candidate->build_id,aspect_build) ||
       candidate->size<=0x593b8d4 || !gate_obs_present(OBS_SMASH_UI_PROJECTION) ||
       !gate_obs_present(OBS_SMASH_UI_DRAW))die("Smash4:3 requires the exact prepared13.0.5 main and UI observation gates");
    aspect_main=candidate;
    const struct { uint32_t offset,word; } admitted[]={
        {0x4f08bc,0x52955568},
        {0x4f08c0,0x72a7f548},
        {0x4f09ac,0x52955576},
        {0x4f09b0,0x72a7f556},
        {0x4fe3bc,0x52955568},
        {0x4fe3c0,0x72a7f548},
        {0x5050ec,0x52955568},
        {0x5050f0,0x72a7f548},
        {0x5145cc,0x52955569},
        {0x5145d0,0x72a7f549},
        {0x51465c,0x52955569},
        {0x514660,0x72a7f549},
        {0x147f0e0,0x52955568},
        {0x147f0e4,0x72a7f548},
        {0x1493090,0x52955568},
        {0x1493094,0x72a7f548},
        {0x14e5efc,0x52955569},
        {0x14e5f00,0x72a7f549},
        {0x14e6014,0xf2d55576},
        {0x14e6018,0xf2e7f556},
        {0x14e64d4,0x52955568},
        {0x14e64d8,0x72a7f548},
        {0x29fabfc,0x5295556f},
        {0x29fac00,0x72a7f54f},
        {0x3158624,0x52955575},
        {0x3158628,0x72a7f555},
        {0x354e2bc,0xd295556c},
        {0x354e2c0,0xf2a7f54c},
        {0x361d3a4,0x52955568},
        {0x361d3a8,0x72a7f548},
        {0x4472c5c,0x3faaaaab},
        {0x44689f4,0x3ab60b61},
        {0x374e114,0x52816c29},
        {0x374e118,0x72a756c9},
        {0x44d64,0xf9400c29},
        {0x378f144,0xa9014ff4},
        {0x3775a1c,0x9100c3e1},
        {0x3775a20,0x97233cd0},
        {0x3743e60,0xd2d1c728},
        {0x3743e64,0xf2e7fc68},
        {0x37c9a5c,0xb2610fe1},
        {0x37c9a9c,0xb2610fe9},
        {0x37c9c50,0xb2610fe9},
        {0x37ca3cc,0xb2610fe8},
        {0x37caf68,0xb2610fe9},
        {0x37c9a6c,0xb27c7be9},
        {0x37c9a78,0xf2c000eb},
        {0x37c9b9c,0x72a000e1},
        {0x37c9a70,0xd2afe40b},
        {0x37c9a74,0xf2afe409},
        {0x37c9b98,0x528fe401},
    };
    for(unsigned i=0;i<sizeof admitted/sizeof admitted[0];++i){
        uint32_t word=0;
        if(!aspect_read(aspect_base()+admitted[i].offset,&word,sizeof word) || word!=admitted[i].word){
            aspect_main=NULL;die("Smash4:3 exact prepared word mismatch at%#x",admitted[i].offset);
        }
    }
    gate_obs_set(OBS_SMASH_UI_PROJECTION,aspect_projection);
    gate_obs_set(OBS_SMASH_UI_DRAW,aspect_draw);
    atomic_store_explicit(&aspect_installed,1,memory_order_release);
    LOG("Smash4:3: exact13.0.5 camera/defaults and scoped UI projection/clipping enabled; physical raster unchanged");
}
