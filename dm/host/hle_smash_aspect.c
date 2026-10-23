// Title/build-scoped UI data corrections before the original SDK copy/draw.
// No executable writes, saved-register changes, generic NVN interception,
// physical raster resizing or simulation timing changes occur here.
#include "dm.h"
#include "smash_aspect.h"
#include "smash_ui_scope.h"
#include "smash_display.h"
#include "smash_camera_policy.h"
#include "smash_camera_owner.h"
#include "smash_projection_policy.h"
#if __has_include("smash_live_rules.generated.h")
#include "smash_live_rules.generated.h"
#define SMASH_PRIVATE_UI_RULES 1
#else
#define SMASH_PRIVATE_UI_RULES 0
#endif
#ifndef DM_GAME_SMASH_LIVE_DISPLAY
#define DM_GAME_SMASH_LIVE_DISPLAY 0
#endif
#if DM_GAME_SMASH_LIVE_DISPLAY && !SMASH_PRIVATE_UI_RULES
#error Shipping Smash live display requires its source-bound private rule header
#endif
#include <math.h>
#include <stdatomic.h>

static module_t *aspect_main;
static _Atomic int aspect_installed;
static _Atomic uint64_t projection_count, perspective_count, draw_count, reject_count;
#if SMASH_PRIVATE_UI_RULES
static int live_display_apply;
#endif
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
void dm_smash_aspect_prepare_interval(const dm_smash_display_geometry_t *geometry){
#if SMASH_PRIVATE_UI_RULES
    if(!live_display_apply || !aspect_main || !geometry)return;
    int admitted=dm_smash_camera_prepare_owner(aspect_base()+0x52b8f00,aspect_read,dm_guest_write_prepare,
            (dm_smash_camera_update)(uintptr_t)(aspect_base()+0x4ec800),geometry->aspect);
    dm_smash_display_note_camera_state(geometry->aspect,geometry->generation,admitted);
#else
    (void)geometry;
#endif
}
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

// Explicit private diagnostics only: discover receiving loaded layout identity
// without mutating it. Reads use the normal mapped-guest admission boundary.
static void aspect_diag_tree(uint64_t pointer,unsigned depth,unsigned *budget) {
    if(!pointer || depth>12 || !*budget)return;
    uint8_t pane[0xd8];if(!aspect_read(pointer,pane,sizeof pane))return;
    --*budget;
    char name[26]={0};memcpy(name,pane+0xb0,25);
    uint64_t table=0,parent=0,next=0,calculate=0,find=0,nested=0,nested_table=0;
    float values[10];memcpy(&table,pane,8);memcpy(&parent,pane+0x18,8);
    memcpy(&next,pane+0x28,8);memcpy(values,pane+0x30,sizeof values);
    aspect_read(table+0x60,&find,8);aspect_read(table+0x98,&calculate,8);
    if(table==aspect_base()+0x4f3f928 && aspect_read(pointer+0xe8,&nested,8) && nested){
        uint64_t nested_root=0,nested_name=0;char label[96]={0};
        aspect_read(nested,&nested_table,8);aspect_read(nested+0x18,&nested_root,8);
        aspect_read(nested+0x30,&nested_name,8);
        for(unsigned i=0;nested_name && i<sizeof label-1;++i){
            if(!aspect_read(nested_name+i,label+i,1)){label[i]=0;break;}
            if(!label[i])break;
        }
        LOG("Smash live Parts: pane=%s layoutclass=main+%#llx layout_name=%s root_is_self=%d",
            name,(unsigned long long)(nested_table-aspect_base()),label,nested_root==pointer);
    }
    LOG("Smash live tree: depth=%u pane=%s class=main+%#llx find=main+%#llx calc=main+%#llx parent=%p xy=%.3f,%.3f scale=%.3f,%.3f size=%.3f,%.3f origin=%u nestedclass=main+%#llx",
        depth,name,(unsigned long long)(table-aspect_base()),(unsigned long long)(find-aspect_base()),
        (unsigned long long)(calculate-aspect_base()),(void *)(uintptr_t)parent,
        values[0],values[1],values[6],values[7],values[8],values[9],pane[0x5b],
        (unsigned long long)(nested_table?nested_table-aspect_base():0));
    uint64_t sentinel=pointer+0x20;
    while(next && next!=sentinel && *budget){
        if(next<8)break;
        uint64_t child=next-8,actual_parent=0,following=0;
        if(!aspect_read(child+0x18,&actual_parent,8) || actual_parent!=pointer ||
           !aspect_read(next+8,&following,8) || following==next)break;
        aspect_diag_tree(child,depth+1,budget);next=following;
    }
}

static void aspect_live_diag(uint64_t di) {
    const char *enabled=getenv("DM_SMASH_LIVE_DIAG");
    if(!enabled || strcmp(enabled,"1"))return;
    static _Atomic uint64_t seen[64];
    uint64_t layout=0,table=0,root=0,name=0;
    if(di<0x50 || !aspect_read(di+0x408,&layout,8) || !layout ||
       !aspect_read(layout,&table,8) || !aspect_read(layout+0x18,&root,8) ||
       !aspect_read(layout+0x30,&name,8))return;
    int inserted=0;
    for(unsigned i=0;i<64;++i){
        uint64_t expected=atomic_load(&seen[i]);
        if(expected==layout)return;
        if(!expected && atomic_compare_exchange_strong(&seen[i],&expected,layout)){inserted=1;break;}
        if(expected==layout)return;
    }
    if(!inserted)return;
    char label[96]={0},rootname[26]={0};uint8_t pane[0xd8];
    for(unsigned i=0;i<sizeof label-1 && name;++i){
        if(!aspect_read(name+i,label+i,1)){label[i]=0;break;}
        if(!label[i])break;
    }
    if(!root || !aspect_read(root,pane,sizeof pane))return;
    memcpy(rootname,pane+0xb0,25);
    uint64_t pane_table=0,child=0;memcpy(&pane_table,pane,8);memcpy(&child,pane+0x28,8);
    LOG("Smash live diag: layout=%p class=main+%#llx name=%s root=%s paneclass=main+%#llx children=%p",
        (void *)(uintptr_t)layout,(unsigned long long)(table-aspect_base()),label,rootname,
        (unsigned long long)(pane_table-aspect_base()),(void *)(uintptr_t)child);
    unsigned budget=96;aspect_diag_tree(root,0,&budget);
}

static void aspect_camera_probe(const uint64_t *regs) {
    uint8_t camera[0x144];uint64_t caller=0;
    if(!aspect_read(regs[0],camera,sizeof camera))return;
    memcpy(&caller,(const uint8_t *)regs+808,8);
#if SMASH_PRIVATE_UI_RULES
    if(live_display_apply){
        float aspect=0,fov=0,near=0,far=0;uint16_t flags=0;
        memcpy(&aspect,camera+0x128,4);memcpy(&fov,camera+0x124,4);memcpy(&near,camera+0x110,4);memcpy(&far,camera+0x118,4);memcpy(&flags,camera+0x12c,2);
        if(dm_smash_world_camera(caller-aspect_base(),flags,aspect,fov,near,far)){
            dm_smash_display_geometry_t geometry;dm_smash_display_active(&geometry);float value=(float)geometry.aspect;
            if(value!=aspect){dm_guest_write_prepare((void *)(uintptr_t)(regs[0]+0x128),4);memcpy((void *)(uintptr_t)(regs[0]+0x128),&value,4);}
            dm_smash_display_note_camera(value,geometry.generation);
        }
    }
#endif
    static _Atomic uint64_t callers[64];int inserted=0;
    for(unsigned i=0;i<64;++i){
        uint64_t expected=atomic_load(&callers[i]);if(expected==caller)return;
        if(!expected && atomic_compare_exchange_strong(&callers[i],&expected,caller)){inserted=1;break;}
    }
    if(!inserted)return;
    float fov=0,aspect=0,near=0,far=0;uint16_t flags=0;
    memcpy(&fov,camera+0x124,4);memcpy(&aspect,camera+0x128,4);
    memcpy(&near,camera+0x110,4);memcpy(&far,camera+0x118,4);memcpy(&flags,camera+0x12c,2);
    LOG("Smash live camera probe: caller=main+%#llx camera=%p aspect=%.7f fov=%.5f near=%.5f far=%.5f flags=%#x",
        (unsigned long long)(caller-aspect_base()),(void *)(uintptr_t)regs[0],aspect,fov,near,far,flags);
}

static _Thread_local struct { uint64_t layout,di,context,generation;double aspect;int admitted; } calculate_probe_stack[32];
static _Thread_local unsigned calculate_probe_depth;
static _Atomic unsigned calculate_probe_logged;
#if SMASH_PRIVATE_UI_RULES
static int ui_scope_ready;
static double ui_scope_aspect=4.0/3.0;
#endif
static void aspect_calculate_probe(const uint64_t *regs) {
    // Exact4b654 is after59f90 constructs the0x28-byte context. The receiving
    // prologue places FP=SP+0x50; the observation and common gate consume816
    // bytes, independently locating that context at regs+824 and FP-0x48.
    uint64_t layout=regs[20],di=regs[19],root=0,table=0,saved_fp=0;
    memcpy(&saved_fp,(const uint8_t *)regs+800,8);
    uint64_t context=(uint64_t)(uintptr_t)regs+824;
    uint8_t context_bytes[0x28];uint64_t context_layout=0;
    if(regs[29]!=saved_fp || regs[29]!=context+0x48 ||
       !aspect_read(context,context_bytes,sizeof context_bytes) ||
       !aspect_read(layout+0x18,&root,8) || !root)return;
    memcpy(&context_layout,context_bytes+0x20,8);
    if(context_layout!=layout)return;
    if(calculate_probe_depth>=32)return;
    double actual_aspect=4.0/3.0;uint64_t generation=0;int ui_admitted=0;
#if SMASH_PRIVATE_UI_RULES
    if(ui_scope_ready){
        unsigned perspective=0;uint64_t owner=0;aspect_read(di+0x408,&owner,8);
        int primary=aspect_owner(di,&perspective) && owner==layout;
        dm_smash_display_geometry_t geometry;dm_smash_display_active(&geometry);
        actual_aspect=live_display_apply?geometry.aspect:ui_scope_aspect;generation=geometry.generation;
        ui_admitted=dm_smash_ui_begin(layout,di,context,regs[29],primary,actual_aspect,
            geometry.insets[0]/geometry.height,geometry.insets[2]/geometry.height,
            geometry.insets[1]/geometry.width,geometry.insets[3]/geometry.width,live_display_apply);
    }
#endif
    calculate_probe_stack[calculate_probe_depth].layout=layout;
    calculate_probe_stack[calculate_probe_depth].di=di;
    calculate_probe_stack[calculate_probe_depth].aspect=actual_aspect;
    calculate_probe_stack[calculate_probe_depth].generation=generation;
    calculate_probe_stack[calculate_probe_depth].admitted=ui_admitted;
    calculate_probe_stack[calculate_probe_depth++].context=context;
    if(!aspect_read(layout,&table,8))return;
    if(atomic_fetch_add(&calculate_probe_logged,1)<12){
        unsigned perspective=0;uint64_t owner_layout=0;
        float scales[2];memcpy(scales,context_bytes+0x10,8);
        int owner=aspect_owner(di,&perspective);
        aspect_read(di+0x408,&owner_layout,8);
        LOG("Smash live Calculate probe: depth=%u layoutclass=main+%#llx primary=%d matching_owner=%d perspective=%u context_matches=1 location=%u,%.6f,%.6f",
            calculate_probe_depth,(unsigned long long)(table-aspect_base()),owner,owner_layout==layout,perspective,
            context_bytes[0x1c],scales[0],scales[1]);
    }
    aspect_live_diag(di);
}
static void aspect_calculated_probe(const uint64_t *regs) {
#if SMASH_PRIVATE_UI_RULES
    if(ui_scope_ready)dm_smash_ui_end(regs[20],regs[19],regs[29]);
#endif
    if(!calculate_probe_depth)return;
    unsigned top=calculate_probe_depth-1;
    uint64_t layout=calculate_probe_stack[top].layout,di=calculate_probe_stack[top].di,current=0;
    if(layout!=regs[20] || di!=regs[19]){
        LOG("Smash live Calculate probe: FRAME MISMATCH depth=%u",calculate_probe_depth);return;
    }
#if SMASH_PRIVATE_UI_RULES
    if(live_display_apply)dm_smash_display_note_hud(calculate_probe_stack[top].aspect,calculate_probe_stack[top].generation,calculate_probe_stack[top].admitted);
#endif
    aspect_read(di+0xc0,&current,8);
    if(atomic_load(&calculate_probe_logged)<=12)
        LOG("Smash live Calculated probe: depth=%u current_layout_matches=%d",calculate_probe_depth,current==layout);
    --calculate_probe_depth;
}

static void aspect_pane_matrix_done(const uint64_t *regs){
#if SMASH_PRIVATE_UI_RULES
    if(ui_scope_ready)dm_smash_ui_after_matrix(regs[19],regs[21]);
#else
    (void)regs;
#endif
}
static void aspect_install_live_probes(void) {
    const char *flag=getenv("DM_SMASH_LIVE_DIAG");
    const char *dynamic=DM_GAME_SMASH_LIVE_DISPLAY?"1":getenv("DM_SMASH_DYNAMIC_DISPLAY"),*dry=getenv("DM_SMASH_UI_DRY");
    int requested=(flag && !strcmp(flag,"1")) || (dynamic && !strcmp(dynamic,"1")) || (dry && !strcmp(dry,"1"));
    if(!requested || !gate_obs_present(OBS_SMASH_CAMERA_UPDATE) ||
       !gate_obs_present(OBS_SMASH_UI_CALCULATE) || !gate_obs_present(OBS_SMASH_UI_CALCULATED) ||
       !gate_obs_present(OBS_SMASH_PANE_LOCAL_DONE) || !gate_obs_present(OBS_SMASH_PANE_USER_DONE)){
        if(DM_GAME_SMASH_LIVE_DISPLAY)die("Shipping Smash live display requires the complete receiving observer group");
        return;
    }
    const uint32_t facts[][2]={{0x4ec820,0x79425814},{0x4ee20c,0xbd412a60},{0x4ee244,0xbd014260},
        {0x4b620,0xf9400c08},{0x4b650,0x94003a50},{0x4b660,0xf9404d08},{0x4b670,0xd63f0100},{0x4b684,0xd63f0100},
        {0x587bc,0x94000079},{0x588cc,0xad038a61},{0x588d0,0x3d802660},
        {0x4ee290,0xd0026e48},{0x4ee294,0xf9478108},{0x4ee298,0xf9400108},
        {0x4ee2a4,0x91328109},{0x4ee2a8,0x913f0108},
        {0x3eb6c4,0xf9478108},{0x3eb6c8,0xf9400108},{0x3eb6cc,0x91328109},{0x3eb6d0,0x9138c108},
        {0x4ede80,0x39460268},{0x4edec0,0xad4b1e63}};
    for(unsigned i=0;i<sizeof facts/sizeof facts[0];++i){
        uint32_t word=0;if(!aspect_read(aspect_base()+facts[i][0],&word,4) || word!=facts[i][1])
            die("Smash live probe adjacent instruction mismatch");
    }
    gate_obs_set(OBS_SMASH_CAMERA_UPDATE,aspect_camera_probe);
    gate_obs_set(OBS_SMASH_UI_CALCULATE,aspect_calculate_probe);
    gate_obs_set(OBS_SMASH_UI_CALCULATED,aspect_calculated_probe);
    gate_obs_set(OBS_SMASH_PANE_LOCAL_DONE,aspect_pane_matrix_done);
    gate_obs_set(OBS_SMASH_PANE_USER_DONE,aspect_pane_matrix_done);
#if SMASH_PRIVATE_UI_RULES
    if((dry && !strcmp(dry,"1")) || (dynamic && !strcmp(dynamic,"1"))){
        const char *target=getenv("DM_SMASH_UI_TARGET_ASPECT");
        if(target){char *end=NULL;double value=strtod(target,&end);if(end && !*end && isfinite(value) && value>=1 && value<=4)ui_scope_aspect=value;}
        const uint32_t local_facts[][2]={{0x589a0,0xf9400c0b},{0x589a4,0xf9400428},{0x589a8,0x9101c169},{0x589ac,0xf100017f},
            {0x58de8,0xad039003},{0x58dec,0x3d802405},{0x58df0,0xd65f03c0}};
        for(unsigned i=0;i<sizeof local_facts/sizeof *local_facts;++i){uint32_t word=0;
            if(!aspect_read(aspect_base()+local_facts[i][0],&word,4) || word!=local_facts[i][1])die("Smash native Local admission failed");}
        dm_smash_ui_setup(aspect_base(),aspect_read,dm_guest_write_prepare,
            (dm_smash_ui_local)(uintptr_t)(aspect_base()+0x589a0),smash_ui_layouts,smash_ui_layout_count);
        live_display_apply=dynamic && !strcmp(dynamic,"1");
        if(live_display_apply){
            for(unsigned i=0;i<sizeof dm_smash_world_camera_callers/sizeof *dm_smash_world_camera_callers;++i){
                uint32_t word=0,offset=dm_smash_world_camera_callers[i]-4;
                uint32_t expected=0x94000000u|((uint32_t)(((int64_t)0x4ec800-offset)/4)&0x3ffffffu);
                if(!aspect_read(aspect_base()+offset,&word,4) || word!=expected)die("Smash world-camera final caller admission failed");
            }
            dm_smash_display_enable();
        }
        ui_scope_ready=1;LOG("Smash UI source rules: %zu layouts; post-derived global correction %s",smash_ui_layout_count,live_display_apply?"ON":"dry");
    }
#endif
    LOG("Smash display: exact camera/Calculate/post-matrix observation group installed");
}

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
#if SMASH_PRIVATE_UI_RULES
    if(live_display_apply){
        dm_smash_display_geometry_t geometry;dm_smash_display_active(&geometry);
        // The exact UI projection uses an unmixed Y row. Keep X/Z and the
        // horizontal extent, then derive the vertical extent from this same
        // guest interval as the pane calculation and world camera.
        if(!dm_smash_ui_projection(matrix,matrix,perspective,geometry.aspect)){
            dm_smash_display_note_projection(geometry.generation,0);aspect_reject();return;
        }
        dm_guest_write_prepare((void *)(uintptr_t)regs[1],sizeof matrix);
        memcpy((void *)(uintptr_t)regs[1],matrix,sizeof matrix);
        dm_smash_display_note_projection(geometry.generation,1);
    }
#endif
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
    aspect_live_diag(regs[0]);
    int32_t config[2],rect[4]; uint8_t override=0;
    if (!aspect_read(aspect_base()+0x523d480,config,sizeof config) ||
        !aspect_read(aspect_base()+0x593b8d4,&override,sizeof override)) { aspect_reject(); return; }
    if(override) { config[0]=1920;config[1]=1080; }
    if (!aspect_rect(config[0],config[1],(unsigned)regs[2],rect)) { aspect_reject(); return; }
    int32_t logical[2]={1920,1440};
#if SMASH_PRIVATE_UI_RULES
    if(live_display_apply){dm_smash_display_geometry_t geometry;dm_smash_display_active(&geometry);
        logical[1]=(int32_t)lround(1920/geometry.aspect);
        // SetProjection is called at layout load, not for each frame. The
        // admitted owner keeps this matrix at DrawInfo+0x10. Revalidate its
        // current shape and refresh Y before the original draw consumes it.
        float projection[16];
        if(aspect_read(regs[0]+0x10,projection,sizeof projection) &&
           dm_smash_ui_projection(projection,projection,perspective,geometry.aspect)){
            dm_guest_write_prepare((void *)(uintptr_t)(regs[0]+0x10),sizeof projection);
            memcpy((void *)(uintptr_t)(regs[0]+0x10),projection,sizeof projection);
            dm_smash_display_note_projection(geometry.generation,1);
        }else dm_smash_display_note_projection(geometry.generation,0);
    }
#endif
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
    aspect_install_live_probes();
    LOG("Smash4:3: exact13.0.5 camera/defaults and scoped UI projection/clipping enabled; physical raster unchanged");
}
