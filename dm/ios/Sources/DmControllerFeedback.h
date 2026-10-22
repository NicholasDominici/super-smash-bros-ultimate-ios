// Each physical player owns independent motion, authored rumble and trigger leases.
#pragma once
#import <GameController/GameController.h>
void dm_controller_feedback_attach(GCController *controller);
void dm_controller_feedback_focus(int active);
void dm_controller_feedback_travel(float left, float right);

// Player slots are stable during a connection; attach nil before replacing one.
void dm_controller_feedback_attach_player(unsigned player, GCController *controller);
void dm_controller_feedback_travel_player(unsigned player, GCController *controller, float left, float right);
