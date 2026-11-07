package org.firstinspires.ftc.teamcode.alea;

/**
 * The numbers the aim assist and the launch look-up table use, in one place.
 * Field values duplicate alea/game/biobuzz.py; tests/test_robot_contract.py keeps them equal.
 * Units are in the names: _IN inches, _DEG degrees, _TICKS_PER_SEC flywheel ticks per second.
 */
public final class Constants {
    private Constants() {}

    // ---- Launcher ----
    /** 6000 RPM Yellow Jacket, 28 ticks/rev: 6000 / 60 * 28. */
    public static final double LAUNCHER_MAX_TICKS_PER_SEC = 2800;
    /** The launcher fires out the back of the robot. */
    public static final double LAUNCHER_YAW_DEG = 180;
    /** The ball leaves the curved hood's top end this far behind the robot's centre (robot model). */
    public static final double LAUNCHER_EXIT_BEHIND_IN = 6.1;
    /** The curved hood turns the ball to this many degrees above level (measured in Onshape). */
    public static final double LAUNCH_ANGLE_DEG = 72.2;

    // ---- Field (inches, 0..141.3 on both axes, FTCodeSim / Pedro frame) ----
    /**
     * Each hive's raised-cell mouth (where to aim): red hive at x 58.0, blue at 83.5; the mouth
     * is at y 54.47 when the audience-side cell is up, 87.03 when the rear one is.
     * From the sim's hive, which matches FIRST's field CAD (via dsim) to ~0.3 in.
     */
    public static final double RED_HIVE_X_IN = 58.0;
    public static final double BLUE_HIVE_X_IN = 83.5;
    public static final double HIVE_AUDIENCE_MOUTH_Y_IN = 54.47;
    public static final double HIVE_REAR_MOUTH_Y_IN = 87.03;
    /** Which hive is aimed at when the OpMode starts. */
    public static final boolean START_TARGET_RED = true;

    /**
     * Where the robot is placed at the start, field inches and degrees counter-clockwise.
     * Same as the sim's default start: red side, front bumper on the audience wall, right
     * under the red hive's raised cell, launcher pointing at it.
     */
    public static final double START_X_IN = 56;
    public static final double START_Y_IN = 10.5;
    public static final double START_HEADING_DEG = -92.7;

    // ---- Odometry ----
    /** Hardware name of the goBILDA Pinpoint in the Robot Configuration. */
    public static final String PINPOINT_NAME = "pinpoint";

    // ---- Look-up table ----
    /**
     * THE LUT: distance from the launcher exit to the cell mouth (inches) -> flywheel speed
     * (ticks/s). FROM THE SIM, 72.2 deg hood: every spot on a 4 in grid, all four targets
     * (red/blue hive, either cell raised), each speed the median middle of the windows that
     * score at that distance (~80 ticks/s wide). The steep shot comes DOWN into the mouth, so
     * the speed is lowest at ~32-36 in and grows both closer and farther.
     * UNVERIFIED on the real robot: re-measure each row on the field and replace it.
     */
    public static final double[] LUT_DISTANCE_IN  = {  24,   28,   32,   36,   40,   44,   48,   52,   56,   60,   64,   68,   72,   76,   80};
    public static final double[] LUT_TICKS_PER_SEC = {1180, 1110, 1100, 1100, 1120, 1140, 1160, 1180, 1200, 1230, 1260, 1290, 1310, 1340, 1360};

    // ---- Auto aim ----
    /** Heading PD: turn power per radian of error, and per rad/s of turning (damping). */
    public static final double AIM_KP = 1.5;
    public static final double AIM_KD = 0.12;
    /** Most turn power the aim uses, and the least it uses while still off target (friction). */
    public static final double AIM_MAX_TURN = 0.6;
    public static final double AIM_MIN_TURN = 0.06;
    /**
     * Shots only from within this many degrees of straight out of the cell's open end. From
     * the sim: 0-75 deg off ~95% of spots score, 90-120 deg 16-38%, past 120 deg none.
     */
    public static final double AIM_MAX_OFF_AXIS_DEG = 80;
    /** Aimed = within this of the target heading. ~1 deg = 1.4 in sideways at 80 in. */
    public static final double AIM_TOLERANCE_DEG = 1.0;
}
