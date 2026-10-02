"""Packed ctypes translation of the official RaceRoom API 3.5 layout.

Source: https://github.com/kwstudios-sweden/r3e-api/blob/
29a3e9587d95edf70f6e32e40db317c6a9d0d5ef/sample-c/src/r3e.h

The upstream repository is released under the Unlicense.  Field order and
packing in this module are ABI, not style: changing either breaks mapped data.
"""

import ctypes

from .constants import MAX_DRIVERS, PIT_MENU_ITEM_COUNT, TIRE_COUNT


Int32 = ctypes.c_int32
Float32 = ctypes.c_float
Float64 = ctypes.c_double
U8Char = ctypes.c_uint8


class PackedStructure(ctypes.Structure):
    _pack_ = 1


class Vec3F32(PackedStructure):
    _fields_ = [("x", Float32), ("y", Float32), ("z", Float32)]


class Vec3F64(PackedStructure):
    _fields_ = [("x", Float64), ("y", Float64), ("z", Float64)]


class OrientationF32(PackedStructure):
    _fields_ = [("pitch", Float32), ("yaw", Float32), ("roll", Float32)]


class SectorStarts(PackedStructure):
    _fields_ = [
        ("sector1", Float32),
        ("sector2", Float32),
        ("sector3", Float32),
    ]


class R3EPlayerData(PackedStructure):
    _fields_ = [
        ("user_id", Int32),
        ("game_simulation_ticks", Int32),
        ("game_simulation_time", Float64),
        ("position", Vec3F64),
        ("velocity", Vec3F64),
        ("local_velocity", Vec3F64),
        ("acceleration", Vec3F64),
        ("local_acceleration", Vec3F64),
        ("orientation", Vec3F64),
        ("rotation", Vec3F64),
        ("angular_acceleration", Vec3F64),
        ("angular_velocity", Vec3F64),
        ("local_angular_velocity", Vec3F64),
        ("local_g_force", Vec3F64),
        ("steering_force", Float64),
        ("steering_force_percentage", Float64),
        ("engine_torque", Float64),
        ("current_downforce", Float64),
        ("voltage", Float64),
        ("ers_level", Float64),
        ("power_mgu_h", Float64),
        ("power_mgu_k", Float64),
        ("torque_mgu_k", Float64),
        ("suspension_deflection", Float64 * TIRE_COUNT),
        ("suspension_velocity", Float64 * TIRE_COUNT),
        ("camber", Float64 * TIRE_COUNT),
        ("ride_height", Float64 * TIRE_COUNT),
        ("front_wing_height", Float64),
        ("front_roll_angle", Float64),
        ("rear_roll_angle", Float64),
        ("third_spring_suspension_deflection_front", Float64),
        ("third_spring_suspension_velocity_front", Float64),
        ("third_spring_suspension_deflection_rear", Float64),
        ("third_spring_suspension_velocity_rear", Float64),
        ("unused1", Float64),
        ("unused2", Float64),
        ("unused3", Float64),
    ]


class R3EFlags(PackedStructure):
    _fields_ = [
        ("yellow", Int32),
        ("yellow_caused_it", Int32),
        ("yellow_overtake", Int32),
        ("yellow_positions_gained", Int32),
        ("sector_yellow", Int32 * 3),
        ("closest_yellow_distance_into_track", Float32),
        ("blue", Int32),
        ("black", Int32),
        ("green", Int32),
        ("checkered", Int32),
        ("white", Int32),
        ("black_and_white", Int32),
    ]


class R3ECarDamage(PackedStructure):
    _fields_ = [
        ("engine", Float32),
        ("transmission", Float32),
        ("aerodynamics", Float32),
        ("suspension", Float32),
        ("unused1", Float32),
        ("unused2", Float32),
    ]


class R3ECutTrackPenalties(PackedStructure):
    _fields_ = [
        ("drive_through", Float32),
        ("stop_and_go", Float32),
        ("pit_stop", Float32),
        ("time_deduction", Float32),
        ("slow_down", Float32),
    ]


class R3EDRS(PackedStructure):
    _fields_ = [
        ("equipped", Int32),
        ("available", Int32),
        ("num_activations_left", Int32),
        ("engaged", Int32),
    ]


class R3EPushToPass(PackedStructure):
    _fields_ = [
        ("available", Int32),
        ("engaged", Int32),
        ("amount_left", Int32),
        ("engaged_time_left", Float32),
        ("wait_time_left", Float32),
    ]


class R3ETireTemp(PackedStructure):
    _fields_ = [
        ("current_temp", Float32 * 3),
        ("optimal_temp", Float32),
        ("cold_temp", Float32),
        ("hot_temp", Float32),
    ]


class R3EBrakeTemp(PackedStructure):
    _fields_ = [
        ("current_temp", Float32),
        ("optimal_temp", Float32),
        ("cold_temp", Float32),
        ("hot_temp", Float32),
    ]


class R3EAidSettings(PackedStructure):
    _fields_ = [
        ("abs", Int32),
        ("tc", Int32),
        ("esp", Int32),
        ("countersteer", Int32),
        ("cornering", Int32),
    ]


class R3EDriverInfo(PackedStructure):
    _fields_ = [
        ("name", U8Char * 64),
        ("car_number", Int32),
        ("class_id", Int32),
        ("model_id", Int32),
        ("team_id", Int32),
        ("livery_id", Int32),
        ("manufacturer_id", Int32),
        ("user_id", Int32),
        ("slot_id", Int32),
        ("class_performance_index", Int32),
        ("engine_type", Int32),
        ("car_width", Float32),
        ("car_length", Float32),
        ("rating", Float32),
        ("reputation", Float32),
        ("unused1", Float32),
        ("unused2", Float32),
    ]


class R3EDriverData(PackedStructure):
    _fields_ = [
        ("driver_info", R3EDriverInfo),
        ("finish_status", Int32),
        ("place", Int32),
        ("place_class", Int32),
        ("lap_distance", Float32),
        ("lap_distance_fraction", Float32),
        ("position", Vec3F32),
        ("track_sector", Int32),
        ("completed_laps", Int32),
        ("current_lap_valid", Int32),
        ("lap_time_current_self", Float32),
        ("sector_time_current_self", Float32 * 3),
        ("sector_time_previous_self", Float32 * 3),
        ("sector_time_best_self", Float32 * 3),
        ("time_delta_front", Float32),
        ("time_delta_behind", Float32),
        ("pitstop_status", Int32),
        ("in_pitlane", Int32),
        ("num_pitstops", Int32),
        ("penalties", R3ECutTrackPenalties),
        ("car_speed", Float32),
        ("tire_type_front", Int32),
        ("tire_type_rear", Int32),
        ("tire_subtype_front", Int32),
        ("tire_subtype_rear", Int32),
        ("base_penalty_weight", Float32),
        ("aid_penalty_weight", Float32),
        ("drs_state", Int32),
        ("ptp_state", Int32),
        ("virtual_energy", Float32),
        ("penalty_type", Int32),
        ("penalty_reason", Int32),
        ("engine_state", Int32),
        ("orientation", Vec3F32),
        ("unused1", Float32),
        ("unused2", Float32),
        ("unused3", Float32),
    ]


class R3EShared(PackedStructure):
    _fields_ = [
        ("version_major", Int32),
        ("version_minor", Int32),
        ("all_drivers_offset", Int32),
        ("driver_data_size", Int32),
        ("game_mode", Int32),
        ("game_paused", Int32),
        ("game_in_menus", Int32),
        ("game_in_replay", Int32),
        ("game_using_vr", Int32),
        ("game_player_in_garage", Int32),
        ("player", R3EPlayerData),
        ("track_name", U8Char * 64),
        ("layout_name", U8Char * 64),
        ("track_id", Int32),
        ("layout_id", Int32),
        ("layout_length", Float32),
        ("sector_start_factors", SectorStarts),
        ("race_session_laps", Int32 * 3),
        ("race_session_minutes", Int32 * 3),
        ("event_index", Int32),
        ("session_type", Int32),
        ("session_iteration", Int32),
        ("session_length_format", Int32),
        ("session_pit_speed_limit", Float32),
        ("session_phase", Int32),
        ("start_lights", Int32),
        ("tire_wear_active", Int32),
        ("fuel_use_active", Int32),
        ("number_of_laps", Int32),
        ("session_time_duration", Float32),
        ("session_time_remaining", Float32),
        ("max_incident_points", Int32),
        ("event_unused1", Float32),
        ("event_unused2", Float32),
        ("pit_window_status", Int32),
        ("pit_window_start", Int32),
        ("pit_window_end", Int32),
        ("in_pitlane", Int32),
        ("pit_menu_selection", Int32),
        ("pit_menu_state", Int32 * PIT_MENU_ITEM_COUNT),
        ("pit_state", Int32),
        ("pit_total_duration", Float32),
        ("pit_elapsed_time", Float32),
        ("pit_action", Int32),
        ("num_pitstops", Int32),
        ("pit_min_duration_total", Float32),
        ("pit_min_duration_left", Float32),
        ("flags", R3EFlags),
        ("position", Int32),
        ("position_class", Int32),
        ("finish_status", Int32),
        ("cut_track_warnings", Int32),
        ("penalties", R3ECutTrackPenalties),
        ("num_penalties", Int32),
        ("completed_laps", Int32),
        ("current_lap_valid", Int32),
        ("track_sector", Int32),
        ("lap_distance", Float32),
        ("lap_distance_fraction", Float32),
        ("lap_time_best_leader", Float32),
        ("lap_time_best_leader_class", Float32),
        ("session_best_lap_sector_times", Float32 * 3),
        ("lap_time_best_self", Float32),
        ("sector_time_best_self", Float32 * 3),
        ("lap_time_previous_self", Float32),
        ("sector_time_previous_self", Float32 * 3),
        ("lap_time_current_self", Float32),
        ("sector_time_current_self", Float32 * 3),
        ("lap_time_delta_leader", Float32),
        ("lap_time_delta_leader_class", Float32),
        ("time_delta_front", Float32),
        ("time_delta_behind", Float32),
        ("time_delta_best_self", Float32),
        ("best_individual_sector_time_self", Float32 * 3),
        ("best_individual_sector_time_leader", Float32 * 3),
        ("best_individual_sector_time_leader_class", Float32 * 3),
        ("incident_points", Int32),
        ("lap_valid_state", Int32),
        ("prev_lap_valid", Int32),
        ("discharge_rate", Float32),
        ("brake_regen", Float32),
        ("unused1", Float32),
        ("vehicle_info", R3EDriverInfo),
        ("player_name", U8Char * 64),
        ("control_type", Int32),
        ("car_speed", Float32),
        ("engine_rps", Float32),
        ("max_engine_rps", Float32),
        ("upshift_rps", Float32),
        ("gear", Int32),
        ("num_gears", Int32),
        ("car_cg_location", Vec3F32),
        ("car_orientation", OrientationF32),
        ("local_acceleration", Vec3F32),
        ("total_mass", Float32),
        ("fuel_left", Float32),
        ("fuel_capacity", Float32),
        ("fuel_per_lap", Float32),
        ("virtual_energy_left", Float32),
        ("virtual_energy_capacity", Float32),
        ("virtual_energy_per_lap", Float32),
        ("engine_temp", Float32),
        ("engine_oil_temp", Float32),
        ("fuel_pressure", Float32),
        ("engine_oil_pressure", Float32),
        ("turbo_pressure", Float32),
        ("throttle", Float32),
        ("throttle_raw", Float32),
        ("brake", Float32),
        ("brake_raw", Float32),
        ("clutch", Float32),
        ("clutch_raw", Float32),
        ("steer_input_raw", Float32),
        ("steer_lock_degrees", Int32),
        ("steer_wheel_range_degrees", Int32),
        ("aid_settings", R3EAidSettings),
        ("drs", R3EDRS),
        ("pit_limiter", Int32),
        ("push_to_pass", R3EPushToPass),
        ("brake_bias", Float32),
        ("drs_num_activations_total", Int32),
        ("ptp_num_activations_total", Int32),
        ("battery_soc", Float32),
        ("water_left", Float32),
        ("abs_setting", Int32),
        ("headlights", Int32),
        ("steer_wheel_max_rotation", Int32),
        ("tire_type", Int32),
        ("tire_rps", Float32 * TIRE_COUNT),
        ("tire_speed", Float32 * TIRE_COUNT),
        ("tire_grip", Float32 * TIRE_COUNT),
        ("tire_wear", Float32 * TIRE_COUNT),
        ("tire_flatspot", Int32 * TIRE_COUNT),
        ("tire_pressure", Float32 * TIRE_COUNT),
        ("tire_dirt", Float32 * TIRE_COUNT),
        ("tire_temp", R3ETireTemp * TIRE_COUNT),
        ("tire_type_front", Int32),
        ("tire_type_rear", Int32),
        ("tire_subtype_front", Int32),
        ("tire_subtype_rear", Int32),
        ("brake_temp", R3EBrakeTemp * TIRE_COUNT),
        ("brake_pressure", Float32 * TIRE_COUNT),
        ("traction_control_setting", Int32),
        ("engine_map_setting", Int32),
        ("engine_brake_setting", Int32),
        ("traction_control_percent", Float32),
        ("tire_on_mtrl", Int32 * TIRE_COUNT),
        ("tire_load", Float32 * TIRE_COUNT),
        ("car_damage", R3ECarDamage),
        ("num_cars", Int32),
        ("all_drivers_data", R3EDriverData * MAX_DRIVERS),
    ]


SHARED_MEMORY_SIZE = ctypes.sizeof(R3EShared)
PLAYER_TICK_OFFSET = (
    R3EShared.player.offset + R3EPlayerData.game_simulation_ticks.offset
)


def decode_u8_string(value: ctypes.Array) -> str:
    """Decode a fixed UTF-8 buffer up to its first NUL byte."""

    raw = bytes(value)
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")
