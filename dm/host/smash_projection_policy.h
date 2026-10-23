// Prepared Smash UI has a fixed horizontal extent. Its live DrawInfo projection
// can remain cached for thousands of frames; derive Y absolutely on every draw.
#pragma once
#include <math.h>
#include <string.h>
static inline int dm_smash_ui_projection(float out[16],const float input[16],unsigned perspective,double aspect){
    if(!isfinite(aspect) || aspect<=1.00001 || aspect>4 || perspective>1)return 0;
    float value[16];memcpy(value,input,sizeof value);
    for(unsigned i=0;i<16;++i)if(!isfinite(value[i]))return 0;
    if(value[0]<=0 || value[0]>10000 || value[5]<=0 || value[5]>10000 || value[4]!=0 || value[6]!=0 || value[7]!=0)return 0;
    if(perspective){if(value[14]!=-1 || value[15]!=0)return 0;}
    else if(fabsf(value[0]-2.f/1920.f)>1.e-8f || value[14]!=0 || value[15]!=1)return 0;
    value[5]=(float)(value[0]*aspect);memcpy(out,value,sizeof value);return 1;
}
