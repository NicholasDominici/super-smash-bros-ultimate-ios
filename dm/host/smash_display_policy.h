// Shipping qualification: the prepared4:3 pair supports narrow landscape
// gameplay. Other scene aspects and unadmitted owners use the coherent baseline.
#pragma once
#include "smash_display.h"
#include <math.h>
static inline double dm_smash_display_target(double aspect,int baseline){
    return !baseline && aspect>=4./3.-1.e-6 && aspect<=1.5+1.e-6?aspect:4./3.;
}
static inline dm_smash_display_geometry_t dm_smash_display_fit(dm_smash_display_geometry_t raw,double aspect){
    dm_smash_display_geometry_t out=raw;
    double w=fmin(raw.width,raw.height*aspect),h=w/aspect,x=(raw.width-w)/2,y=(raw.height-h)/2;
    out.width=w;out.height=h;out.aspect=aspect;
    out.insets[0]=fmax(0,raw.insets[0]-y);out.insets[2]=fmax(0,raw.insets[2]-y);
    out.insets[1]=fmax(0,raw.insets[1]-x);out.insets[3]=fmax(0,raw.insets[3]-x);
    return out;
}
