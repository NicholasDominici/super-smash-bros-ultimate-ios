// Representative derived Text reflow, native post-matrix ordering, unchanged
// UserMatrix state, zero-write admission failure and nonblocking dry overlap.
#include <assert.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "smash_ui_scope.h"
#define K(a,b,c,d) ((uint32_t)(a)|((uint32_t)(b)<<8)|((uint32_t)(c)<<16)|((uint32_t)(d)<<24))
typedef struct {
    unsigned char layout[0x80],root[0xd8],bg[0xd8],label[0xd8],child[0xd8],time[0xd8],context[0x28];
    float identity[12],user[12];char name[32];
} fixture;
static fixture data;
static unsigned char *module;
static const size_t module_size=0x5242000;
static _Atomic unsigned writes,reflows;
static uint64_t get64(const void *p,size_t at){uint64_t v;memcpy(&v,(const char *)p+at,8);return v;}
static float getf(const void *p,size_t at){float v;memcpy(&v,(const char *)p+at,4);return v;}
static void ptr(void *p,size_t at,const void *v){memcpy((char *)p+at,&v,8);}
static void flt(void *p,size_t at,float v){memcpy((char *)p+at,&v,4);}
static int contains(uint64_t at,size_t n,const void *p,size_t size){uint64_t b=(uintptr_t)p;return at>=b && n<=size && at-b<=size-n;}
static int read_guest(uint64_t at,void *out,size_t n){
    if(!contains(at,n,&data,sizeof data) && !contains(at,n,module,module_size))return 0;
    memcpy(out,(void *)(uintptr_t)at,n);return 1;
}
static void prepare(void *p,size_t n){assert(contains((uintptr_t)p,n,&data,sizeof data));atomic_fetch_add(&writes,1);}
static void multiply(float out[12],const float a[12],const float b[12]){
    float m[12]={0};for(unsigned r=0;r<3;++r)for(unsigned c=0;c<4;++c){for(unsigned k=0;k<3;++k)m[r*4+c]+=a[r*4+k]*b[k*4+c];if(c==3)m[r*4+c]+=a[r*4+3];}memcpy(out,m,sizeof m);
}
static void local(void *p,void *ctx){
    unsigned char *parent=(void *)(uintptr_t)get64(p,0x18);float x=getf(p,0x30),y=getf(p,0x34);
    unsigned origin=((unsigned char *)p)[0x5b];
    if(parent){if((origin>>4&3)==1)x-=getf(parent,0x50)/2;if((origin>>4&3)==2)x+=getf(parent,0x50)/2;
        if((origin>>6)==1)y+=getf(parent,0x54)/2;if((origin>>6)==2)y-=getf(parent,0x54)/2;}
    float m[12]={getf(p,0x48),0,0,x,0,getf(p,0x4c),0,y,0,0,1,getf(p,0x38)},g[12];
    const float *basis=parent?(const float *)(void *)(parent+0x70):(const float *)(uintptr_t)get64(ctx,8);
    multiply(g,basis,m);memcpy((char *)p+0x70,g,sizeof g);
}
static const dm_smash_ui_rule panes[]={
    {.name="RootPane",.kind=K('p','a','n','1')},
    {.name="bg",.parent="RootPane",.kind=K('p','i','c','1'),.grow_y=1},
    {.name="child",.parent="label",.kind=K('p','a','n','1'),.offset_y=256},
    {.name="label",.parent="bg",.kind=K('t','x','t','1')},
    {.name="time",.parent="RootPane",.kind=K('p','a','n','1'),.edge_y=1},
};
static const dm_smash_ui_layout_rule rule={.name="fixture",.resource="synthetic",.root_name="RootPane",.width=1920,.height=1440,.panes=panes,.pane_count=5,.primary=1};
static void pane(unsigned char *p,const char *name,size_t type,unsigned char *parent){
    ptr(p,0,module+type);ptr(p,0x18,parent);ptr(p,0x20,p+0x20);ptr(p,0x28,p+0x20);
    flt(p,0x48,1);flt(p,0x4c,1);flt(p,0x50,1920);flt(p,0x54,1440);p[0x58]=1;p[0x59]=255;strcpy((char *)p+0xb0,name);
}
static void attach(unsigned char *parent,unsigned char *child){ptr(parent,0x20,child+8);ptr(parent,0x28,child+8);ptr(child,8,parent+0x20);ptr(child,0x10,parent+0x20);}
static void reset(void){
    memset(&data,0,sizeof data);strcpy(data.name,"fixture");data.identity[0]=data.identity[5]=data.identity[10]=1;
    memcpy(data.user,data.identity,sizeof data.user);
    ptr(data.layout,0,module+0x523f6f0);ptr(data.layout,0x18,data.root);ptr(data.layout,0x30,data.name);
    flt(data.layout,0x28,1920);flt(data.layout,0x2c,1440);flt(data.context,0x10,1);flt(data.context,0x14,1);ptr(data.context,8,data.identity);
    pane(data.root,"RootPane",0x4f3f810,NULL);pane(data.bg,"bg",0x5240748,data.root);
    pane(data.label,"label",0x5241320,data.bg);pane(data.child,"child",0x4f3f810,data.label);
    flt(data.label,0x54,40);flt(data.label,0x34,23);data.child[0x5b]=0x40;
    attach(data.root,data.bg);attach(data.bg,data.label);attach(data.label,data.child);
    pane(data.time,"time",0x4f3f810,data.root);flt(data.time,0x30,800);
    ptr(data.root,0x20,data.time+8);ptr(data.bg,0x10,data.time+8);ptr(data.time,8,data.bg+8);ptr(data.time,0x10,data.root+0x20);
    atomic_store(&writes,0);atomic_store(&reflows,0);
}
static int begin(uint64_t frame,int apply){return dm_smash_ui_begin((uintptr_t)data.layout,7,(uintptr_t)data.context,frame,1,1.5,0,0,0,0,apply);}
static void end(uint64_t frame){dm_smash_ui_end((uintptr_t)data.layout,7,frame);}
static void calculate(unsigned char *p){
    // Exact receiving predicate: a cached-size mismatch must not gain a fake
    // dirty flag. Natural Text reflow settles size before base Calculate.
    if(p==data.label && (p[0x58]&0x10)){flt(p,0x54,80);atomic_fetch_add(&reflows,1);}
    p[0x58]&=~0x10;
    if(p[0x58]&0x20){
        unsigned char *parent=(void *)(uintptr_t)get64(p,0x18);float g[12];
        multiply(g,parent?(float *)(void *)(parent+0x70):data.identity,(float *)(uintptr_t)get64(p,0xa0));memcpy(p+0x70,g,sizeof g);
    }else local(p,data.context);
    dm_smash_ui_after_matrix((uintptr_t)p,(uintptr_t)data.context);
    for(uint64_t link=get64(p,0x28);link!=(uintptr_t)p+0x20;link=get64((void *)(uintptr_t)link,8))calculate((void *)(uintptr_t)(link-8));
}
static void *other_thread(void *arg){(void)arg;assert(begin(201,0));end(201);return NULL;}
int main(void){
    module=calloc(1,module_size);assert(module);
    const size_t tables[]={0x4f3f810,0x5240748,0x5241320},calcs[]={0x58700,0x379e300,0x37a17f0};
    for(unsigned i=0;i<3;++i){ptr(module+tables[i],0x60,module+0x583c0);ptr(module+tables[i],0x98,module+calcs[i]);}
    dm_smash_ui_setup((uintptr_t)module,read_guest,prepare,local,&rule,1);
    reset();fixture before=data;assert(begin(1,0));assert(!memcmp(&before,&data,sizeof data));assert(!atomic_load(&writes));end(1);
    for(unsigned dirty=0;dirty<2;++dirty){
        reset();if(dirty)data.label[0x58]|=0x10;
        assert(begin(2+dirty,1));assert((data.label[0x58]&0x10)==(dirty?0x10:0));
        calculate(data.root);end(2+dirty);assert(atomic_load(&reflows)==dirty);
        assert(getf(data.label,0x54)==(dirty?80:40));
        float expected=23+(dirty?40:20)+256*((4.f/3.f)/1.5f-1);
        assert(fabsf(getf(data.child,0x70+28)-expected)<.001f);
        unsigned char *nodes[]={data.root,data.bg,data.label,data.child};
        for(unsigned i=0;i<4;++i)assert(!(nodes[i][0x58]&0x60) && !get64(nodes[i],0xa0));
        if(dirty)assert(fabsf((23+20+256*((4.f/3.f)/1.5f-1))-expected)>19.f);
    }
    reset();data.bg[0x58]|=0x20;ptr(data.bg,0xa0,data.user);assert(begin(4,1));calculate(data.root);end(4);
    assert(get64(data.bg,0xa0)==(uintptr_t)data.user && (data.bg[0x58]&0x20));
    reset();assert(begin(5,1));calculate(data.root);assert(begin(6,1));calculate(data.root);end(6);end(5);assert(!get64(data.bg,0xa0));
    for(unsigned which=0;which<5;++which){
        reset();if(which==0)strcpy((char *)data.child+0xb0,"wrong");if(which==1)ptr(data.child,0x18,data.root);
        if(which==2)ptr(data.bg,0,module+1);if(which==3)flt(data.child,0x30,NAN);if(which==4)data.child[0x58]|=0x40;
        before=data;assert(!begin(10+which,1));assert(!atomic_load(&writes) && !memcmp(&before,&data,sizeof data));
        dm_smash_ui_stats a,b;dm_smash_ui_snapshot(&a);
        // Native Calculate still reaches both post sites after a decline. A
        // partially constructed plan must remain ineligible at those sites.
        calculate(data.root);dm_smash_ui_snapshot(&b);
        assert(!atomic_load(&writes) && a.matrix_calls==b.matrix_calls && a.matrix_writes==b.matrix_writes);
        end(10+which);
    }
    reset();assert(begin(80,1));calculate(data.root);unsigned old_writes=atomic_load(&writes);
    strcpy(data.name,"unknown_nested");assert(!begin(81,1));
    calculate(data.root);assert(atomic_load(&writes)==old_writes);end(81);
    strcpy(data.name,"fixture");calculate(data.root);assert(atomic_load(&writes)>old_writes);end(80);
    reset();assert(dm_smash_ui_begin((uintptr_t)data.layout,7,(uintptr_t)data.context,90,1,678./466,0,34./466,0,84./678,1));
    calculate(data.root);end(90);
    float safe_x=800-1920*(84.f/678)*(800.f/1920+.5f);
    assert(fabsf(getf(data.time,0x70+12)-safe_x)<.001f && getf(data.time,0x48)==1 && getf(data.time,0x4c)==1);
    reset();assert(begin(100,0));pthread_t thread;assert(!pthread_create(&thread,NULL,other_thread,NULL));assert(!pthread_join(thread,NULL));end(100);
    dm_smash_ui_stats stats;dm_smash_ui_snapshot(&stats);
    assert(stats.begins==stats.ends && stats.declined==6 && stats.nested==2 && stats.max_depth==2);
    assert(!stats.waits && stats.overlaps==1 && !stats.borrowed && !stats.restored && stats.matrix_writes>0 && stats.pose_changes>0);
    free(module);puts("PASS: post-derived output, Text dirty/reflow/current-parent-size regression, authored user state, nested scopes, zero-write decline, no cross-call waits");return 0;
}
