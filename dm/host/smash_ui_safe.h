// Compress authored HUD anchor positions into the horizontal safe rectangle,
// preserving the geometry/scale of text and icons attached to those anchors.
#pragma once
#include <math.h>
static inline float dm_smash_ui_safe_x(float position,unsigned origin,float width,double left,double right){
    double anchor=position+(origin==1?-width*.5:origin==2?width*.5:0);
    return (float)(width*(left-(left+right)*(anchor/width+.5)));
}
