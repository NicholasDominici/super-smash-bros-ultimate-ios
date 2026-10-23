// Pure affine operation shared by Smash's private native-routine fixture and
// prospective scoped HUD transaction. It has no guest pointers or side effects.
#pragma once
#include <float.h>
#include <math.h>
#include <string.h>

static inline int dm_smash_ui_matrix(float out[12],const float local[12],
                                     const float parent_growth[2],const float own_growth[2]) {
    if(!out || !local || !parent_growth || !own_growth)return 0;
    for(unsigned i=0;i<2;++i)
        if(!isfinite(parent_growth[i]) || !isfinite(own_growth[i]) ||
           parent_growth[i]<.25f || parent_growth[i]>4.f ||
           own_growth[i]<.25f || own_growth[i]>4.f)return 0;
    float next[12];
    for(unsigned row=0;row<3;++row)for(unsigned column=0;column<4;++column){
        unsigned index=row*4+column;
        if(!isfinite(local[index]))return 0;
        double value=(double)local[index]*(column<2?own_growth[column]:1.f)/
            (row<2?parent_growth[row]:1.f);
        if(!isfinite(value) || fabs(value)>FLT_MAX)return 0;
        next[index]=(float)value;
    }
    memcpy(out,next,sizeof next);return 1;
}
