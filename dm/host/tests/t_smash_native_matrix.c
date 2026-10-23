// Private opt-in CPU fixture: execute hash-admitted Smash13.0.5 Calculate and
// Local routines on synthetic panes, optionally through exact rewritten gates
// and the actual production entry.S. No GPU, saves or device proof.
#include <assert.h>
#include <fcntl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <pthread.h>
#include <dlfcn.h>
#include <libkern/OSCacheControl.h>
#include "smash_ui_matrix.h"
#include "smash_ui_scope.h"
#include "smash_camera_owner.h"

typedef float Matrix[12];
typedef struct { _Alignas(16) unsigned char b[0xd8]; } Pane;
typedef void (*Calculate)(void *,void *,void *,unsigned);
typedef void (*Local)(void *,void *);
static const Matrix identity={1,0,0,0,0,1,0,0,0,0,1,0};
static unsigned checks,negative_controls;
static unsigned probe_mode,gate_hits[31];
static uintptr_t gate_returns[31];
static unsigned char *guest_image;static size_t guest_size;
static void *fixture_start;static size_t fixture_size;
static uint64_t deny_tail_at;
extern void dm_gate(void),smash_gate_state_probe(void),smash_test_clobber(void);
void unimpl_c(void){abort();}void dm_thread_returned(void){abort();}
void smash_assert_gate_state(const uint64_t *regs){
    for(unsigned i=0;i<30;++i)if(i!=18){assert(regs[i]==1000+i);++checks;}
    const unsigned char *simd=(const unsigned char *)regs+256;
    for(unsigned i=0;i<32;++i)for(unsigned b=0;b<16;++b){assert(simd[i*16+b]==i+1);++checks;}
    assert(regs[768/8]==0x60000000 && !regs[776/8] && !regs[784/8]);checks+=3;
}
uint64_t gate_dispatch(uint64_t ret,uint64_t *regs){
    if(probe_mode){smash_assert_gate_state(regs);smash_test_clobber();return 0;}
    unsigned number=31;for(unsigned i=0;i<31;++i)if(gate_returns[i]==ret){number=i;break;}
    assert(number==26 || number==29 || number==30);++gate_hits[number];
    if(number!=26)dm_smash_ui_after_matrix(regs[19],regs[21]);smash_test_clobber();return 0;
}
static int contained(uint64_t at,size_t n,const void *p,size_t size){uint64_t b=(uintptr_t)p;return at>=b && n<=size && at-b<=size-n;}
static int read_guest(uint64_t at,void *out,size_t n){
    if(!contained(at,n,guest_image,guest_size) && !contained(at,n,fixture_start,fixture_size))return 0;
    if(deny_tail_at && at<deny_tail_at+0x4c && at+n>deny_tail_at)return 0;
    memcpy(out,(void *)(uintptr_t)at,n);return 1;
}
static void prepare_guest(void *p,size_t n){assert(contained((uintptr_t)p,n,fixture_start,fixture_size));}
static void gates_load(const char *path,unsigned char *image){
    FILE *file=fopen(path,"r");assert(file);char line[256];unsigned found=0;
    while(fgets(line,sizeof line,file)){
        long long off,site;char kind[32];unsigned number;
        if(sscanf(line,"%lli\t%31s\t%u\t%lli",&off,kind,&number,&site)!=4 || strcmp(kind,"obs") || (number!=26 && number!=29 && number!=30))continue;
        assert(!gate_returns[number]);gate_returns[number]=(uintptr_t)(image+off);++found;
    }
    assert(found==3);fclose(file);pthread_key_t key;assert(!pthread_key_create(&key,NULL));
    uint32_t offset=(uint32_t)key*8;memcpy(image+0x7448000+3*8,&offset,4);assert(!pthread_setspecific(key,(void *)dm_gate));
}
static void pointer(void *p,size_t at,const void *v){memcpy((char *)p+at,&v,8);}
static void scalar(void *p,size_t at,float v){memcpy((char *)p+at,&v,4);}
static uint64_t u64(const void *p,size_t at){uint64_t v;memcpy(&v,(const char *)p+at,8);return v;}
static uint32_t u32(const void *p,size_t at){uint32_t v;memcpy(&v,(const char *)p+at,4);return v;}
static void multiply(Matrix out,const Matrix a,const Matrix b){
    Matrix v={0};
    for(unsigned r=0;r<3;++r)for(unsigned c=0;c<4;++c){
        for(unsigned k=0;k<3;++k)v[r*4+c]+=a[r*4+k]*b[k*4+c];
        if(c==3)v[r*4+c]+=a[r*4+3];
    }
    memcpy(out,v,sizeof v);
}
static void equal(const float *a,const float *b){
    for(unsigned i=0;i<12;++i){
        if(!isfinite(a[i]) || !isfinite(b[i]) || fabsf(a[i]-b[i])>.0008f*(1+fabsf(b[i]))){
            fprintf(stderr,"matrix mismatch component%u actual%.9g expected%.9g\n",i,a[i],b[i]);abort();
        }
        ++checks;
    }
}
static unsigned char *read_file(const char *name,size_t *length){
    int fd=open(name,O_RDONLY);assert(fd>=0);struct stat st;assert(!fstat(fd,&st));
    *length=(size_t)st.st_size;unsigned char *v=malloc(*length);assert(v);
    for(size_t done=0;done<*length;){ssize_t n=read(fd,v+done,*length-done);assert(n>0);done+=(size_t)n;}
    close(fd);return v;
}
static uint64_t tag(const unsigned char *image,size_t length,int64_t wanted){
    assert(length>16);uint32_t mod=u32(image,4);assert(mod<length-8 && !memcmp(image+mod,"MOD0",4));
    int32_t delta;memcpy(&delta,image+mod+4,4);uint64_t at=mod+(int64_t)delta;
    while(at<=length-16){int64_t key;memcpy(&key,image+at,8);if(!key)return 0;if(key==wanted)return u64(image,at+8);at+=16;}
    abort();
}
static void *exported(unsigned char *image,size_t length,const char *wanted){
    uint64_t symbols=tag(image,length,6),strings=tag(image,length,5);
    assert(symbols<strings && strings<length);
    for(uint64_t at=symbols;at+24<=strings;at+=24){
        uint32_t name=u32(image,at);uint16_t section;memcpy(&section,image+at+6,2);
        assert(strings+name<length && memchr(image+strings+name,0,length-strings-name));
        if(section && !strcmp((char *)image+strings+name,wanted)){
            uint64_t where=u64(image,at+8);assert(where<length);return image+where;
        }
    }
    fprintf(stderr,"missing exact SDK data export %s\n",wanted);abort();
}
static void relocate(unsigned char *image,size_t length,unsigned char *sdk,size_t sdk_length){
    uint64_t table=tag(image,length,7),bytes=tag(image,length,8);
    assert(table<length && bytes<=length-table && !(bytes%24) && !tag(image,length,36));
    unsigned imports=0;
    const char *names[]={"_ZN2nn4util6detail14FloatDegree180E","_ZN2nn4util6detail19AngleIndexHalfRoundE","_ZN2nn4util6detail17SinCosSampleTableE",
        "_ZN2nn4util6detail15FloatPiDivided2E","_ZN2nn4util6detail7FloatPiE","_ZN2nn4util6detail15SinCoefficientsE","_ZN2nn4util6detail15CosCoefficientsE","_ZN2nn4util6detail16Float1Divided2PiE","_ZN2nn4util6detail8Float2PiE"};
    const uint64_t sites[]={0x52a4340,0x52a4348,0x52a4350,0x52a4760,0x52a4338,0x52a4740,0x52a4748,0x52a4758,0x52a4750};
    uint64_t symbols=tag(image,length,6),strings=tag(image,length,5);
    for(uint64_t at=table;at<table+bytes;at+=24){
        uint64_t where=u64(image,at),info=u64(image,at+8),addend=u64(image,at+16);
        assert(where<=length-8);
        if((uint32_t)info==1027){assert(addend<length);pointer(image,where,image+addend);continue;}
        for(unsigned i=0;i<sizeof sites/sizeof *sites;++i)if(where==sites[i]){
            assert((uint32_t)info==1025 && !addend);
            uint64_t symbol=symbols+(info>>32)*24;assert(symbol+24<=strings);
            uint64_t name=strings+u32(image,symbol);assert(name<length && memchr(image+name,0,length-name));
            assert(!strcmp((char *)image+name,names[i]));
            pointer(image,where,exported(sdk,sdk_length,names[i]));++imports;
        }
    }
    assert(imports==9);
    table=tag(image,length,23);bytes=tag(image,length,2);assert(bytes%24==0 && table+bytes<=length);
    for(uint64_t at=table;at<table+bytes;at+=24){
        uint64_t where=u64(image,at),info=u64(image,at+8);assert((uint32_t)info==1026 && where<=length-8);
        uint64_t name=strings+u32(image,symbols+(info>>32)*24);assert(name<length);
        const char *text=(const char *)image+name;
        const char *math[]={"cosf","sinf","tanf","atanf","atan2f","acosf","asinf","sqrtf"};
        for(unsigned i=0;i<sizeof math/sizeof *math;++i)if(!strcmp(text,math[i])){void *target=dlsym(RTLD_DEFAULT,text);assert(target);pointer(image,where,target);}
    }
}
static void init(Pane *p,void *table,Pane *parent,float angle,unsigned origin){
    memset(p,0,sizeof *p);pointer(p->b,0,table);pointer(p->b,0x18,parent);
    pointer(p->b,0x20,p->b+0x20);pointer(p->b,0x28,p->b+0x20);
    scalar(p->b,0x30,13);scalar(p->b,0x34,-19);scalar(p->b,0x38,5);
    scalar(p->b,0x44,angle);scalar(p->b,0x48,1.2f);scalar(p->b,0x4c,.8f);
    scalar(p->b,0x50,280);scalar(p->b,0x54,210);
    p->b[0x58]=0x11;p->b[0x59]=255;p->b[0x5b]=(unsigned char)origin;
}
static void attach(Pane *parent,Pane *child){
    pointer(parent->b,0x20,child->b+8);pointer(parent->b,0x28,child->b+8);
    pointer(child->b,8,parent->b+0x20);pointer(child->b,0x10,parent->b+0x20);
}
static void native_local(Local local,Matrix out,const Pane *p,const Pane *parent,void *context){
    Pane copy=*p,fake;
    if(parent){fake=*parent;memcpy(fake.b+0x70,identity,sizeof identity);pointer(copy.b,0x18,&fake);}
    else pointer(copy.b,0x18,NULL);
    local(copy.b,context);memcpy(out,copy.b+0x70,sizeof(Matrix));
    assert(!memcmp(copy.b,p->b,0x18));assert(!memcmp(copy.b+0x20,p->b+0x20,0x50));
    assert(!memcmp(copy.b+0xa0,p->b+0xa0,0x38));
}
static void native_scope(unsigned char *image,Calculate calculate,Local local){
    static struct {Pane panes[4];unsigned char context[0x28],layout[0x80],di[0x200];Matrix basis,user;char name[16];} q;
#define K(a,b,c,d) ((uint32_t)(a)|((uint32_t)(b)<<8)|((uint32_t)(c)<<16)|((uint32_t)(d)<<24))
    static const dm_smash_ui_rule rules[]={
        {.name="RootPane",.kind=K('p','a','n','1')},
        {.name="bg",.parent="RootPane",.kind=K('p','a','n','1'),.grow_y=1},
        {.name="child",.parent="bg",.kind=K('p','a','n','1'),.offset_y=128},
        {.name="grand",.parent="child",.kind=K('p','a','n','1')},
    };
    static const dm_smash_ui_layout_rule rule={.name="fixture",.resource="synthetic",.root_name="RootPane",.width=1920,.height=1440,.panes=rules,.pane_count=4,.primary=1};
    fixture_start=&q;fixture_size=sizeof q;dm_smash_ui_setup((uintptr_t)image,read_guest,prepare_guest,local,&rule,1);
    unsigned old29=gate_hits[29],old30=gate_hits[30];
    for(unsigned i=0;i<72;++i){
        memset(&q,0,sizeof q);strcpy(q.name,"fixture");memcpy(q.basis,identity,sizeof identity);memcpy(q.user,identity,sizeof identity);
        pointer(q.context,8,q.basis);scalar(q.context,0x18,1);scalar(q.context,0x10,1);scalar(q.context,0x14,1);
        pointer(q.layout,0,image+0x523f6f0);pointer(q.layout,0x18,q.panes);pointer(q.layout,0x30,q.name);scalar(q.layout,0x28,1920);scalar(q.layout,0x2c,1440);
        const char *names[]={"RootPane","bg","child","grand"};
        for(unsigned j=0;j<4;++j){init(q.panes+j,image+0x4f3f810,j?q.panes+j-1:NULL,j?(float)((i+j*7)%45):0,j==2?(i%3)<<6:0);strcpy((char *)q.panes[j].b+0xb0,names[j]);if(j)attach(q.panes+j-1,q.panes+j);}
        scalar(q.panes[0].b,0x50,1920);scalar(q.panes[0].b,0x54,1440);
        int authored=i%2;if(authored){pointer(q.panes[1].b,0xa0,q.user);q.panes[1].b[0x58]|=0x22;q.panes[1].b[0x59]=128;}
        const double aspects[]={4./3.,678./466,951./669,1.5};
        double aspect=aspects[i%4];float ratio=(float)((4./3)/aspect);const float unit[2]={1,1},grown[2]={1,ratio};
        Matrix expected[4];
        for(unsigned j=0;j<4;++j){
            Pane copy=q.panes[j],parent;Matrix l,u;
            if(j){parent=q.panes[j-1];memcpy(parent.b+0x70,identity,sizeof identity);if(j==2)scalar(parent.b,0x54,210*ratio);pointer(copy.b,0x18,&parent);}
            if(j==2)scalar(copy.b,0x34,-19+128*(ratio-1));
            if(j==1 && authored)memcpy(l,q.user,sizeof l);else {local(copy.b,q.context);memcpy(l,copy.b+0x70,sizeof l);}
            assert(dm_smash_ui_matrix(u,l,j==2?grown:unit,j==1?grown:unit));multiply(expected[j],j?expected[j-1]:identity,u);
        }
        uint64_t frame=i+100;assert(dm_smash_ui_begin((uintptr_t)q.layout,(uintptr_t)q.di,(uintptr_t)q.context,frame,1,aspect,0,0,0,0,1));
        calculate(q.panes[0].b,q.di,q.context,1);dm_smash_ui_end((uintptr_t)q.layout,(uintptr_t)q.di,frame);
        for(unsigned j=0;j<4;++j)equal((float *)(void *)(q.panes[j].b+0x70),expected[j]);
        if(authored){assert(q.panes[2].b[0x5a]==128);++checks;assert(u64(q.panes[1].b,0xa0)==(uintptr_t)q.user && (q.panes[1].b[0x58]&0x20));}
    }
    assert(gate_hits[29]>old29 && gate_hits[30]>old30);
    dm_smash_ui_stats stats;dm_smash_ui_snapshot(&stats);assert(stats.accepted==72 && stats.begins==stats.ends && !stats.declined && stats.matrix_writes);
}
static void native_camera(unsigned char *image){
    static struct {uint64_t slot,holder;unsigned char root[0x1000],replacement[0x1000];} q;
    fixture_start=&q;fixture_size=sizeof q;memset(&q,0,sizeof q);q.slot=(uintptr_t)&q.holder;q.holder=(uintptr_t)q.root;
    unsigned char *camera=q.root+0xca0;
    scalar(camera,0x88,5);scalar(camera,0xb4,1);scalar(camera,0x110,2);scalar(camera,0x118,100000);scalar(camera,0x124,1.0471975512f);scalar(camera,0x128,4.f/3);
    uint16_t flags=0x43;memcpy(camera+0x12c,&flags,2);
    dm_smash_camera_update update=(dm_smash_camera_update)(void *)(image+0x4ec800);
    // The common update observer is registered, but this test has a host caller.
    // It intentionally exercises the original receiving native data routine.
    update(camera); // Prime real native caches before testing the unchanged4:3 endpoint.
    for(unsigned i=0;i<120;++i){const double aspects[]={4./3.,678./466,951./669,1.5};double aspect=aspects[i%4];
        assert(dm_smash_camera_prepare_owner((uintptr_t)&q.slot,read_guest,prepare_guest,update,aspect));
        assert(dm_smash_camera_float(camera,0x128)==(float)aspect);checks+=2;
    }
    memcpy(q.replacement,q.root,sizeof q.root);unsigned char before[0x144];memcpy(before,camera,sizeof before);q.holder=(uintptr_t)q.replacement;
    assert(dm_smash_camera_prepare_owner((uintptr_t)&q.slot,read_guest,prepare_guest,update,951./669));assert(!memcmp(before,camera,sizeof before));checks+=2;
    q.holder=(uintptr_t)q.root;deny_tail_at=(uintptr_t)camera+0x144;unsigned calls=gate_hits[26];
    assert(!dm_smash_camera_prepare_owner((uintptr_t)&q.slot,read_guest,prepare_guest,update,951./669) && gate_hits[26]==calls);deny_tail_at=0;++checks;
    q.holder=0;assert(!dm_smash_camera_prepare_owner((uintptr_t)&q.slot,read_guest,prepare_guest,update,678./466));++checks;
}
int main(int argc,char **argv){
    probe_mode=1;smash_gate_state_probe();probe_mode=0;
    if(argc==2 && !strcmp(argv[1],"--gate-only")){printf("PASS: production entry.S full GPR/SIMD/NZCV/FPSR/FPCR preservation, %u checks\n",checks);return 0;}
    assert(argc==6 || argc==7);size_t raw_length,sdk_length;
    unsigned char *raw=read_file(argv[1],&raw_length),*sdk=read_file(argv[2],&sdk_length);
    size_t image_size=strtoull(argv[3],NULL,0),file_size=strtoull(argv[4],NULL,0),front=strtoull(argv[5],NULL,0);
    assert(front==0x2000000 && file_size==0x52ac000 && image_size==0x744c000 && raw_length>file_size);
    size_t patch_size=raw_length-file_size,mapped=image_size+front;
    unsigned char *mapping=mmap(NULL,mapped,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);assert(mapping!=MAP_FAILED);
    unsigned char *image=mapping+front;memcpy(image,raw,file_size);memcpy(mapping,raw+file_size,patch_size);free(raw);
    relocate(image,image_size,sdk,sdk_length);
    guest_image=image;guest_size=image_size;
    if(argc==7)gates_load(argv[6],image);
    const uint32_t calc_guard[]={0xfc1b0fe8,0xf90007f9,0xa9015ff8,0xa90257f6};
    const uint32_t local_guard[]={0xf9400c0b,0xf9400428,0x9101c169,0xf100017f};
    assert(!memcmp(image+0x58700,calc_guard,sizeof calc_guard));assert(!memcmp(image+0x589a0,local_guard,sizeof local_guard));
    size_t code_length=(0x39c8440+0x3fff)&~(size_t)0x3fff;
    assert(!mprotect(image,code_length,PROT_READ|PROT_EXEC));
    assert(!mprotect(mapping,(patch_size+0x3fff)&~(size_t)0x3fff,PROT_READ|PROT_EXEC));
    sys_icache_invalidate(image,code_length);sys_icache_invalidate(mapping,patch_size);
    Calculate calculate=(Calculate)(void *)(image+0x58700);Local local=(Local)(void *)(image+0x589a0);
    uintptr_t table[32]={0};table[0x98/8]=(uintptr_t)calculate;
    unsigned char context[0x28]={0},di[0x200]={0};pointer(context,8,identity);scalar(context,0x18,1);
    for(unsigned iteration=0;iteration<240;++iteration){
        unsigned ox=iteration%3,oy=(iteration/3)%3,origin=(ox<<4)|(oy<<6);
        Pane root,fill,child,grand;
        init(&root,table,NULL,0,0);init(&fill,table,&root,(float)(iteration%45),origin);
        init(&child,table,&fill,-30,origin);init(&grand,table,&child,17,origin);
        attach(&root,&fill);attach(&fill,&child);attach(&child,&grand);
        Matrix locals[4],globals[4];Pane *panes[]={&root,&fill,&child,&grand};
        for(unsigned i=0;i<4;++i)native_local(local,locals[i],panes[i],i?panes[i-1]:NULL,context);
        memcpy(globals[0],locals[0],sizeof(Matrix));for(unsigned i=1;i<4;++i)multiply(globals[i],globals[i-1],locals[i]);
        calculate(root.b,di,context,1);for(unsigned i=0;i<4;++i)equal((float *)(void *)(panes[i]->b+0x70),globals[i]);
        // Z-rotation and parent-origin coefficients are independently predicted.
        float angle=(float)(iteration%45)*(.017453292519943295f),c=cosf(angle),n=sinf(angle);
        Matrix z={c*1.2f,-n*.8f,0,13+(ox==1?-140.f:ox==2?140.f:0.f),n*1.2f,c*.8f,0,-19+(oy==1?105.f:oy==2?-105.f:0.f),0,0,1,5};
        equal(locals[1],z);
        const float unit[2]={1,1},growth[2]={1.08f,1.04f+iteration*.001f};
        const float *own[]={unit,growth,unit,unit};Matrix adjusted[4];Pane before[4];
        for(unsigned i=0;i<4;++i){
            before[i]=*panes[i];assert(dm_smash_ui_matrix(adjusted[i],locals[i],i?own[i-1]:unit,own[i]));
            pointer(panes[i]->b,0xa0,adjusted[i]);panes[i]->b[0x58]=(panes[i]->b[0x58]|0x30)&~0x40;
        }
        calculate(root.b,di,context,1);
        for(unsigned i=0;i<4;++i){
            Matrix expected;float g[12];memcpy(g,identity,sizeof g);g[0]=own[i][0];g[5]=own[i][1];multiply(expected,globals[i],g);
            equal((float *)(void *)(panes[i]->b+0x70),expected);
            assert(!memcmp(before[i].b+0x30,panes[i]->b+0x30,0x28));
            pointer(panes[i]->b,0xa0,(void *)(uintptr_t)u64(before[i].b,0xa0));
            panes[i]->b[0x58]=(panes[i]->b[0x58]&~0x60)|(before[i].b[0x58]&0x60)|0x10;
        }
        calculate(root.b,di,context,1);for(unsigned i=0;i<4;++i)equal((float *)(void *)(panes[i]->b+0x70),globals[i]);
        // The tempting parent-scale-only change visibly distorts descendants.
        pointer(fill.b,0xa0,adjusted[1]);fill.b[0x58]|=0x20;
        calculate(root.b,di,context,1);int different=0;
        for(unsigned i=0;i<12;++i)different|=fabsf(((float *)(void *)(grand.b+0x70))[i]-globals[3][i])>.001f;
        assert(different);++negative_controls;
    }
    Matrix kept;memcpy(kept,identity,sizeof kept);float invalid[2]={NAN,1},valid[2]={1,1};
    assert(!dm_smash_ui_matrix(kept,identity,invalid,valid));equal(kept,identity);
    if(argc==7){native_scope(image,calculate,local);native_camera(image);}
    printf("{\"status\":\"pass\",\"checks\":%u,\"negative_controls\":%u,\"post_normal_gates\":%u,\"post_user_gates\":%u,\"world_camera_gates\":%u,\"gpu\":false,\"gameplay\":false,\"production_scope\":%s,\"scope\":\"Exact native Calculate/Local/CameraUpdate plus production800-byte gate. Optional rewritten TSD callbacks execute UI correction and120native camera folds, owner replacement and retirement on synthetic data.\"}\n",checks,negative_controls,gate_hits[29],gate_hits[30],gate_hits[26],argc==7?"true":"false");
    assert(!munmap(mapping,mapped));free(sdk);return 0;
}
