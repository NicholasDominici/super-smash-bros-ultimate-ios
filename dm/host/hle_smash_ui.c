// Receiving Smash13.0.5 UI transaction. Validate every required owned pane and
// validate ownership before any output write. Correct the native global matrix
// only after derived reflow and base calculation. No UserMatrix state is borrowed.
#include "dm.h"
#include "smash_ui_scope.h"
#include "smash_ui_matrix.h"
#include "smash_ui_safe.h"
#include <stdatomic.h>
#include <math.h>

enum { UI_LIMIT=4096,UI_DEPTH=64,UI_NESTING=8 };
#define KIND(a,b,c,d) ((uint32_t)(a)|((uint32_t)(b)<<8)|((uint32_t)(c)<<16)|((uint32_t)(d)<<24))
typedef struct {
    uint64_t pointer,parent,table;
    const dm_smash_ui_rule *rule;
    unsigned char bytes[0xd8],saved_flags;
    float growth[2];
    int touch,primary_root;
} ui_node;
typedef struct ui_scope {
    struct ui_scope *previous;
    uint64_t layout,di,frame,context;
    ui_node *nodes;
    size_t count,capacity;
    double ratio,top,bottom,left,right;
    int apply,committed,admitted;
    const dm_smash_ui_layout_rule *owner;
} ui_scope;
typedef struct {
    const dm_smash_ui_layout_rule *owner;
    unsigned char *seen;
    size_t matched;
} ui_binding;
static struct {
    uint64_t base;
    dm_smash_ui_read read;
    dm_smash_ui_prepare prepare;
    dm_smash_ui_local local;
    const dm_smash_ui_layout_rule *rules;
    size_t count;
} ui_config;
// No guest state is borrowed and no thread waits across guest code. Disjoint
// trees can Calculate concurrently. A bounded method-lifetime registry rejects
// overlapping active corrections without inventing a guest-lock dependency.
static pthread_mutex_t ui_mu=PTHREAD_MUTEX_INITIALIZER;
static struct {ui_scope *scope;pthread_t thread;} ui_scopes[64];
static _Thread_local ui_scope *ui_current;
static _Atomic uint64_t ui_begins,ui_ends,ui_accepted,ui_declined,ui_borrowed,ui_restored,ui_nested,ui_max_depth,ui_waits;
static _Atomic uint64_t ui_pose_changes;
static _Atomic uint64_t ui_matrix_calls,ui_matrix_writes;
static _Atomic uint64_t ui_overlaps;
static uint64_t read64(const void *p,size_t at){uint64_t v;memcpy(&v,(const char *)p+at,8);return v;}
static float readfloat(const void *p,size_t at){float v;memcpy(&v,(const char *)p+at,4);return v;}
static void put64(void *p,size_t at,uint64_t v){memcpy((char *)p+at,&v,8);}
static void putfloat(void *p,size_t at,float v){memcpy((char *)p+at,&v,4);}
static int read_string(uint64_t pointer,char out[96]){
    memset(out,0,96);
    if(!pointer)return 0;
    for(unsigned i=0;i<96;++i){if(!ui_config.read(pointer+i,out+i,1))return 0;if(!out[i])return i>0;}
    out[95]=0;return 0;
}
static uint32_t pane_kind(uint64_t table){
    static const struct {uint32_t table,calculate,kind;} classes[]={
        {0x4f3f810,0x58700,KIND('p','a','n','1')},{0x4f3f928,0x58700,KIND('p','r','t','1')},
        {0x4f18e48,0x58700,KIND('b','n','d','1')},{0x523ffe8,0x58700,KIND('b','n','d','1')},
        {0x523e300,0x378d3d0,KIND('b','n','d','1')},{0x5240748,0x379e300,KIND('p','i','c','1')},
        {0x52400d8,0x5efe0,KIND('p','i','c','1')},{0x5241320,0x37a17f0,KIND('t','x','t','1')},
        {0x5241540,0x37a4010,KIND('w','n','d','1')},
    };
    for(unsigned i=0;i<sizeof classes/sizeof *classes;++i)if(table==ui_config.base+classes[i].table){
        uint64_t find=0,calc=0;
        if(ui_config.read(table+0x60,&find,8) && ui_config.read(table+0x98,&calc,8) &&
           find==ui_config.base+0x583c0 && calc==ui_config.base+classes[i].calculate)return classes[i].kind;
    }
    return 0;
}
static const dm_smash_ui_rule *find_rule(const dm_smash_ui_layout_rule *layout,const char *name){
    size_t lo=0,hi=layout->pane_count;
    while(lo<hi){size_t mid=(lo+hi)/2;int order=strcmp(name,layout->panes[mid].name);if(!order)return layout->panes+mid;if(order<0)hi=mid;else lo=mid+1;}
    return NULL;
}
static ui_node *find_node(ui_scope *scope,uint64_t pointer){
    for(size_t i=0;i<scope->count;++i)if(scope->nodes[i].pointer==pointer)return scope->nodes+i;
    return NULL;
}
static ui_node *add_node(ui_scope *scope,uint64_t pointer,const unsigned char bytes[0xd8],const dm_smash_ui_rule *rule){
    ui_node *existing=find_node(scope,pointer);if(existing)return existing;
    if(scope->count==UI_LIMIT)return NULL;
    if(scope->count==scope->capacity){
        size_t capacity=scope->capacity?scope->capacity*2:64;
        if(capacity>UI_LIMIT)capacity=UI_LIMIT;
        void *next=realloc(scope->nodes,capacity*sizeof *scope->nodes);if(!next)return NULL;
        scope->nodes=next;scope->capacity=capacity;
    }
    ui_node *node=scope->nodes+scope->count++;memset(node,0,sizeof *node);
    node->pointer=pointer;node->parent=read64(bytes,0x18);node->table=read64(bytes,0);
    node->rule=rule;memcpy(node->bytes,bytes,0xd8);node->saved_flags=bytes[0x58];
    node->growth[0]=rule && rule->grow_x?(float)(1+scope->ratio):1.f;
    node->growth[1]=rule && rule->grow_y?(float)(1+scope->ratio):1.f;
    return node;
}
static int walk_owner(ui_scope *,ui_binding *,uint64_t,int,unsigned);
static int walk_layout(ui_scope *,const dm_smash_ui_layout_rule *,uint64_t,int,unsigned);
static int child_links(ui_scope *scope,ui_binding *binding,uint64_t pointer,
                       const char *parent_name,int owned,unsigned depth){
    uint64_t sentinel=pointer+0x20,first=0,last=0,previous=sentinel;
    if(!ui_config.read(pointer+0x28,&first,8) || !ui_config.read(pointer+0x20,&last,8))return 0;
    size_t count=0;
    for(uint64_t link=first;link!=sentinel;){
        if(!link || link<8 || ++count>UI_LIMIT)return 0;
        uint64_t before=0,after=0,child=link-8;unsigned char bytes[0xd8];
        if(!ui_config.read(child,bytes,sizeof bytes) || !ui_config.read(link,&before,8) ||
           !ui_config.read(link+8,&after,8) || before!=previous || after==link || read64(bytes,0x18)!=pointer)return 0;
        if(owned){
            if(!walk_owner(scope,binding,child,0,depth+1))return 0;
            ui_node *node=find_node(scope,child);
            if(!node || !node->rule || !node->rule->parent || strcmp(node->rule->parent,parent_name))return 0;
        }else{
            if(!pane_kind(read64(bytes,0)) || !memchr(bytes+0xb0,0,25) || !add_node(scope,child,bytes,NULL))return 0;
        }
        previous=link;link=after;
    }
    return last==previous;
}
static int walk_owner(ui_scope *scope,ui_binding *binding,uint64_t pointer,int alias,unsigned depth){
    if(depth>UI_DEPTH)return 0;
    const dm_smash_ui_layout_rule *owner=binding->owner;
    unsigned char bytes[0xd8];if(!pointer || !ui_config.read(pointer,bytes,sizeof bytes) || !memchr(bytes+0xb0,0,25))return 0;
    const char *name=alias?owner->root_name:(const char *)bytes+0xb0;
    const dm_smash_ui_rule *rule=find_rule(owner,name);uint32_t kind=pane_kind(read64(bytes,0));
    if(!rule || (!alias && kind!=rule->kind) || (alias && kind!=KIND('p','r','t','1')))return 0;
    size_t rule_index=(size_t)(rule-owner->panes);
    if(binding->seen[rule_index])return 0;
    binding->seen[rule_index]=1;++binding->matched;
    // Repeated native pointers are admitted only for the Parts object doubling
    // as its child Layout's root. No other alias/cycle or duplicated name passes.
    ui_node *prior=find_node(scope,pointer);if(prior && !alias)return 0;
    if(alias && (rule->offset_x || rule->offset_y || rule->grow_x || rule->grow_y))return 0;
    ui_node *node=add_node(scope,pointer,bytes,rule);if(!node)return 0;
    if(!rule->parent && owner->primary){
        if(node->parent || readfloat(bytes,0x50)!=owner->width || readfloat(bytes,0x54)!=owner->height)return 0;
        node->primary_root=1;
    }
    if(kind==KIND('p','r','t','1') && !alias){
        uint64_t layout=0,table=0,root=0,text=0;float dimensions[2];char label[96];
        if(!rule->parts || !ui_config.read(pointer+0xe8,&layout,8) || !layout ||
           !ui_config.read(layout,&table,8) || table!=ui_config.base+0x523f6f0 ||
           !ui_config.read(layout+0x18,&root,8) || root!=pointer ||
           !ui_config.read(layout+0x28,dimensions,8) || !ui_config.read(layout+0x30,&text,8) || !read_string(text,label))return 0;
        char localized[96];snprintf(localized,sizeof localized,"%s+us_en",rule->parts);
        if(strcmp(label,rule->parts) && strcmp(label,localized))return 0;
        if(rule->visit_parts){
            const dm_smash_ui_layout_rule *child=NULL;
            for(size_t i=0;i<ui_config.count;++i){
                const dm_smash_ui_layout_rule *candidate=ui_config.rules+i;
                if(!candidate->primary && !strcmp(candidate->resource,owner->resource) && !strcmp(candidate->name,label) &&
                   dimensions[0]==candidate->width && dimensions[1]==candidate->height){if(child)return 0;child=candidate;}
            }
            if(!child || !walk_layout(scope,child,pointer,1,depth+1))return 0;
        }else if(node->growth[0]!=1.f || node->growth[1]!=1.f){
            if(!child_links(scope,NULL,pointer,NULL,0,depth))return 0;
        }
        return 1;
    }
    // Count and parent/name membership are checked independently of native
    // sibling ordering, which the game can change for draw order.
    return child_links(scope,binding,pointer,rule->name,1,depth);
}
static int walk_layout(ui_scope *scope,const dm_smash_ui_layout_rule *owner,uint64_t root,int alias,unsigned depth){
    if(!owner->pane_count || owner->pane_count>UI_LIMIT)return 0;
    ui_binding binding={.owner=owner,.seen=calloc(owner->pane_count,1)};
    if(!binding.seen)return 0;
    int ok=walk_owner(scope,&binding,root,alias,depth) && binding.matched==owner->pane_count;
    free(binding.seen);return ok;
}
static int plan_scope(ui_scope *scope,const dm_smash_ui_layout_rule *owner,uint64_t root){
    scope->count=0;scope->owner=owner;
    if(!walk_layout(scope,owner,root,0,0))return 0;
    unsigned char context[0x28];if(!ui_config.read(scope->context,context,sizeof context))return 0;
    if(context[0x1c]>1 || !isfinite(readfloat(context,0x10)) || !isfinite(readfloat(context,0x14)))return 0;
    const float unit[2]={1,1};
    for(size_t i=0;i<scope->count;++i){
        ui_node *node=scope->nodes+i,*parent=find_node(scope,node->parent);
        const float *parent_growth=parent?parent->growth:unit;
        float dx=node->rule?(float)(node->rule->offset_x*scope->ratio):0;
        float dy=node->rule?(float)(node->rule->offset_y*scope->ratio):0;
        // Only the explicit edge-anchor rules acquire safe-area displacement.
        // Fill-origin offsets represent geometry, not content-safe anchors.
        if(node->rule && node->rule->edge_y)dy+=(float)(node->rule->edge_y>0?-scope->top:scope->bottom);
        int safe_horizontal=node->rule && node->rule->edge_y && parent && parent->primary_root && (scope->left || scope->right);
        int virtual_parent=parent && parent->primary_root && scope->ratio && (node->bytes[0x5b]&0xc0);
        node->touch=dx || dy || safe_horizontal || node->growth[0]!=1 || node->growth[1]!=1 || parent_growth[0]!=1 || parent_growth[1]!=1 || virtual_parent;
        if(!node->touch)continue;
        if((node->saved_flags&0x40) && (dx || dy || safe_horizontal || node->growth[0]!=1 || node->growth[1]!=1))return 0;
        for(unsigned at=0x30;at<0x58;at+=4)if(!isfinite(readfloat(node->bytes,at)) || fabsf(readfloat(node->bytes,at))>1.e7f)return 0;
    }
    return 1;
}
void dm_smash_ui_setup(uint64_t base,dm_smash_ui_read read,dm_smash_ui_prepare prepare,
                       dm_smash_ui_local local,const dm_smash_ui_layout_rule *rules,size_t count){
    pthread_mutex_lock(&ui_mu);for(unsigned i=0;i<64;++i)if(ui_scopes[i].scope)die("Smash UI configuration changed during Calculate");
    ui_config.base=base;ui_config.read=read;ui_config.prepare=prepare;ui_config.local=local;ui_config.rules=rules;ui_config.count=count;
    pthread_mutex_unlock(&ui_mu);
}
int dm_smash_ui_begin(uint64_t layout,uint64_t di,uint64_t context,uint64_t frame,
                      int primary,double aspect,double safe_top,double safe_bottom,double safe_left,double safe_right,int apply){
    if(!ui_config.count)return 0;
    unsigned depth=1;for(ui_scope *previous=ui_current;previous;previous=previous->previous)++depth;
    if(depth>UI_NESTING)die("Smash UI Calculate nesting exceeds admitted bound");
    if(depth>1)atomic_fetch_add(&ui_nested,1);
    uint64_t maximum=atomic_load(&ui_max_depth);while(depth>maximum && !atomic_compare_exchange_weak(&ui_max_depth,&maximum,depth)){}
    ui_scope *scope=calloc(1,sizeof *scope);if(!scope)die("Smash UI scope allocation failed");
    scope->previous=ui_current;scope->layout=layout;scope->di=di;scope->frame=frame;scope->context=context;
    scope->ratio=(4.0/3.0)/aspect-1;scope->top=safe_top;scope->bottom=safe_bottom;scope->left=safe_left;scope->right=safe_right;scope->apply=apply;ui_current=scope;
    atomic_fetch_add(&ui_begins,1);
    if(!primary)return 0;
    uint64_t text=0,root=0,table=0;float dimensions[2];char label[96]={0};
    int accepted=0;
    if(isfinite(aspect) && aspect>=1 && aspect<=4 && isfinite(safe_top) && isfinite(safe_bottom) && isfinite(safe_left) && isfinite(safe_right) &&
       safe_top>=0 && safe_bottom>=0 && safe_left>=0 && safe_right>=0 && safe_top+safe_bottom<1 && safe_left+safe_right<1 &&
       ui_config.read(layout,&table,8) && table==ui_config.base+0x523f6f0 &&
       ui_config.read(layout+0x30,&text,8) && read_string(text,label) && ui_config.read(layout+0x18,&root,8) &&
       ui_config.read(layout+0x28,dimensions,8)){
        for(size_t i=0;i<ui_config.count;++i){const dm_smash_ui_layout_rule *rule=ui_config.rules+i;
            if(rule->primary && !strcmp(label,rule->name) && dimensions[0]==rule->width && dimensions[1]==rule->height && plan_scope(scope,rule,root)){accepted=1;break;}
        }
    }
    if(!accepted){uint64_t n=atomic_fetch_add(&ui_declined,1);if(n<24)LOG("Smash UI scope declined before writes: %s",text?label:"unreadable");return 0;}
    pthread_mutex_lock(&ui_mu);unsigned empty=64;
    for(unsigned i=0;i<64;++i){
        ui_scope *other=ui_scopes[i].scope;if(!other){if(empty==64)empty=i;continue;}
        if(pthread_equal(ui_scopes[i].thread,pthread_self()))continue;
        int overlap=0;for(size_t j=0;j<scope->count && !overlap;++j)overlap=find_node(other,scope->nodes[j].pointer)!=NULL;
        if(overlap){atomic_fetch_add(&ui_overlaps,1);if(apply || other->apply){pthread_mutex_unlock(&ui_mu);die("Smash UI unsupported concurrent same-pane Calculate");}}
    }
    if(empty==64){pthread_mutex_unlock(&ui_mu);die("Smash UI scope reservation capacity exceeded");}
    ui_scopes[empty].scope=scope;ui_scopes[empty].thread=pthread_self();pthread_mutex_unlock(&ui_mu);
    scope->admitted=1;
    atomic_fetch_add(&ui_accepted,1);
    if(!apply)return 1;
    // Plain root invalidation asks the SDK to refresh its transform tree. Text
    // sees original flags/pointers, performs reflow, then our base post-hook uses
    // its current dimensions. This flag follows native dirty-bit semantics.
    ui_config.prepare((void *)(uintptr_t)(root+0x58),1);
    ((unsigned char *)(uintptr_t)root)[0x58]|=0x10;
    scope->committed=1;return 1;
}
void dm_smash_ui_after_matrix(uint64_t pointer,uint64_t context_pointer){
    ui_scope *scope=ui_current;ui_node *node=NULL;
    // A declined nested call is an explicit native-only scope. It must not
    // accidentally reuse either its partial plan or an accepted outer plan.
    if(!scope || !scope->admitted)return;
    for(;scope;scope=scope->previous)if((node=find_node(scope,pointer)))break;
    if(!scope || !node || !node->touch)return;
    atomic_fetch_add(&ui_matrix_calls,1);
    unsigned char current[0xd8],context[0x28],fake[0xd8];float local[12],adjusted[12],basis[12],global[12];
    if(!ui_config.read(pointer,current,sizeof current) || read64(current,0)!=node->table || read64(current,0x18)!=node->parent ||
       memcmp(current+0xb0,node->bytes+0xb0,25) || !ui_config.read(context_pointer,context,sizeof context))die("Smash post-matrix ownership/context changed");
    if(memcmp(current+0x30,node->bytes+0x30,0x28))atomic_fetch_add(&ui_pose_changes,1);
    if(current[0x58]&0x40){
        if(node->rule && (node->rule->offset_x || node->rule->offset_y || node->rule->grow_x || node->rule->grow_y))
            die("Smash post-matrix unsupported authored global mode");
        return; // Absolute user globals already ignore inherited parent growth.
    }
    ui_node *parent=find_node(scope,node->parent);const float unit[2]={1,1};
    const float *parent_growth=parent?parent->growth:unit;
    float dx=node->rule?(float)(node->rule->offset_x*scope->ratio):0;
    float dy=node->rule?(float)(node->rule->offset_y*scope->ratio):0;
    if(node->rule && node->rule->edge_y)dy+=(float)((node->rule->edge_y>0?-scope->top:scope->bottom)*scope->owner->height*(1+scope->ratio));
    if(node->rule && node->rule->edge_y && parent && parent->primary_root)
        dx+=dm_smash_ui_safe_x(readfloat(current,0x30),(current[0x5b]>>4)&3,scope->owner->width,scope->left,scope->right);
    if(current[0x58]&0x20){
        if(!ui_config.read(read64(current,0xa0),local,sizeof local))die("Smash authored local matrix unmapped");
        local[3]+=dx;local[7]+=dy;
    }else{
        unsigned char copy[0xd8];memcpy(copy,current,sizeof copy);memset(fake,0,sizeof fake);
        if(node->parent && !ui_config.read(node->parent,fake,sizeof fake))die("Smash post-matrix parent unmapped");
        const float identity[12]={1,0,0,0,0,1,0,0,0,0,1,0};memcpy(fake+0x70,identity,sizeof identity);
        put64(copy,0x18,(uint64_t)(uintptr_t)fake);
        putfloat(fake,0x50,readfloat(fake,0x50)*parent_growth[0]);
        putfloat(fake,0x54,readfloat(fake,0x54)*(parent && parent->primary_root?(float)(1+scope->ratio):parent_growth[1]));
        putfloat(copy,0x30,readfloat(copy,0x30)+dx);putfloat(copy,0x34,readfloat(copy,0x34)+dy);
        ui_config.local(copy,context);memcpy(local,copy+0x70,sizeof local);
    }
    if(!dm_smash_ui_matrix(adjusted,local,parent_growth,node->growth))die("Smash post-matrix nonfinite native local");
    uint64_t basis_pointer=node->parent?node->parent+0x70:read64(context,8);
    if(!ui_config.read(basis_pointer,basis,sizeof basis))die("Smash post-matrix basis unmapped");
    for(unsigned r=0;r<3;++r)for(unsigned c=0;c<4;++c){
        double value=c==3?basis[r*4+3]:0;
        for(unsigned k=0;k<3;++k)value+=(double)basis[r*4+k]*adjusted[k*4+c];
        if(!isfinite(value) || fabs(value)>FLT_MAX)die("Smash post-matrix nonfinite composed global");
        global[r*4+c]=(float)value;
    }
    if(scope->committed){ui_config.prepare((void *)(uintptr_t)(pointer+0x70),sizeof global);memcpy((void *)(uintptr_t)(pointer+0x70),global,sizeof global);atomic_fetch_add(&ui_matrix_writes,1);}
}
void dm_smash_ui_end(uint64_t layout,uint64_t di,uint64_t frame){
    ui_scope *scope=ui_current;if(!scope || scope->frame!=frame)return;
    if(scope->layout!=layout || scope->di!=di)die("Smash UI Calculate scope return identity changed");
    if(!scope->apply)for(size_t i=0;i<scope->count;++i){ui_node *node=scope->nodes+i;unsigned char pose[0x28];
        if(!ui_config.read(node->pointer+0x30,pose,sizeof pose))die("Smash UI pane unmapped during native Calculate");
        if(memcmp(pose,node->bytes+0x30,sizeof pose)){
            uint64_t count=atomic_fetch_add(&ui_pose_changes,1);
            if(count<16)LOG("Smash UI custom Calculate changed local pose: layout=%s pane=%s",scope->owner?scope->owner->name:"unknown",node->bytes+0xb0);
        }
    }
    pthread_mutex_lock(&ui_mu);for(unsigned i=0;i<64;++i)if(ui_scopes[i].scope==scope)ui_scopes[i].scope=NULL;pthread_mutex_unlock(&ui_mu);
    ui_current=scope->previous;free(scope->nodes);free(scope);atomic_fetch_add(&ui_ends,1);
    if(atomic_load(&ui_ends)%600==0){dm_smash_ui_stats st;dm_smash_ui_snapshot(&st);
        LOG("Smash UI scope totals: begins=%llu ends=%llu accepted=%llu declined=%llu borrowed=%llu restored=%llu nested=%llu max_depth=%llu waits=%llu pose_changes=%llu",
            (unsigned long long)st.begins,(unsigned long long)st.ends,(unsigned long long)st.accepted,(unsigned long long)st.declined,
            (unsigned long long)st.borrowed,(unsigned long long)st.restored,(unsigned long long)st.nested,(unsigned long long)st.max_depth,(unsigned long long)st.waits,(unsigned long long)st.pose_changes);
    }
}
void dm_smash_ui_snapshot(dm_smash_ui_stats *out){
    if(out)*out=(dm_smash_ui_stats){atomic_load(&ui_begins),atomic_load(&ui_ends),atomic_load(&ui_accepted),atomic_load(&ui_declined),atomic_load(&ui_borrowed),atomic_load(&ui_restored),atomic_load(&ui_nested),atomic_load(&ui_max_depth),atomic_load(&ui_waits),atomic_load(&ui_pose_changes),atomic_load(&ui_matrix_calls),atomic_load(&ui_matrix_writes),atomic_load(&ui_overlaps)};
}
