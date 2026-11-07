package org.firstinspires.ftc.teamcode.alea;

import org.psilynx.psikit.core.Logger;

/**
 * Auto heading + LUT shot. Given where the robot is (from odometry), it works out:
 *   - which way the robot must face so the launcher (out the BACK) points at the target cell,
 *   - a turn command that gets it there (a PD controller on the heading error),
 *   - how far the launcher is from the cell, and the LUT flywheel speed for that distance.
 *
 * The target is the raised cell's open mouth of the chosen hive. Which cell of a hive is
 * raised changes every time it tips, so the driver flips it with a button (Teleop: dpad up).
 *
 * Pure math, no hardware: call update() once per loop with the odometry pose.
 * Field frame: inches, the same as FTCodeSim / Pedro (0..141 on both axes), heading in
 * radians counter-clockwise.
 */
public class AimAssist {

    /**
     * Each hive's raised-cell mouth, field inches (from the sim's hive, matching FIRST's CAD),
     * and which way the mouth faces: toward the audience wall (-y) or the rear wall (+y).
     */
    public enum Target {
        RED_AUDIENCE(Constants.RED_HIVE_X_IN, Constants.HIVE_AUDIENCE_MOUTH_Y_IN, -1),
        RED_REAR(Constants.RED_HIVE_X_IN, Constants.HIVE_REAR_MOUTH_Y_IN, +1),
        BLUE_AUDIENCE(Constants.BLUE_HIVE_X_IN, Constants.HIVE_AUDIENCE_MOUTH_Y_IN, -1),
        BLUE_REAR(Constants.BLUE_HIVE_X_IN, Constants.HIVE_REAR_MOUTH_Y_IN, +1);

        public final double x, y;
        public final int facesY;
        Target(double x, double y, int facesY) { this.x = x; this.y = y; this.facesY = facesY; }

        public boolean red() { return this == RED_AUDIENCE || this == RED_REAR; }
        public boolean audience() { return this == RED_AUDIENCE || this == BLUE_AUDIENCE; }

        static Target of(boolean red, boolean audience) {
            if (red) return audience ? RED_AUDIENCE : RED_REAR;
            return audience ? BLUE_AUDIENCE : BLUE_REAR;
        }
    }

    // ---- Fields ----

    private final LaunchLut lut;
    private Target target;

    // results of the last update()
    private boolean havePose = false;
    private double targetHeading, headingError, distance, offAxis, turn, lutSpeed;

    // ---- Constructor ----

    public AimAssist(LaunchLut lut, Target start) {
        this.lut = lut;
        this.target = start;
    }

    // ---- Target selection ----

    public void setAlliance(boolean red) { target = Target.of(red, target.audience()); }

    /** The hive tipped: its other cell is now the raised one. */
    public void flipRaisedCell() { target = Target.of(target.red(), !target.audience()); }

    public Target getTarget() { return target; }

    // ---- Periodic ----

    /**
     * @param x, y           robot centre, field inches
     * @param heading        radians, counter-clockwise
     * @param headingVel     radians/s, counter-clockwise (for the D term)
     */
    public void update(double x, double y, double heading, double headingVel) {
        havePose = true;
        double dx = target.x - x, dy = target.y - y;
        // The launcher fires out the back, so the robot faces directly AWAY from the target.
        targetHeading = Math.atan2(dy, dx) + Math.toRadians(Constants.LAUNCHER_YAW_DEG);
        headingError = wrap(targetHeading - heading);

        // PD on heading. Derivative on the measured turn rate, so a target change is no kick.
        double u = Constants.AIM_KP * headingError - Constants.AIM_KD * headingVel;
        // Friction needs a little power before the robot turns at all.
        if (Math.abs(headingError) > Math.toRadians(Constants.AIM_TOLERANCE_DEG) && Math.abs(u) < Constants.AIM_MIN_TURN)
            u = Math.copySign(Constants.AIM_MIN_TURN, u);
        u = Math.max(-Constants.AIM_MAX_TURN, Math.min(Constants.AIM_MAX_TURN, u));
        // drivetrain.drive()'s turn input is like the right stick: positive turns CLOCKWISE.
        turn = -u;

        // The ball leaves the hood this far behind the robot's centre, i.e. this much closer.
        distance = Math.hypot(dx, dy) - Constants.LAUNCHER_EXIT_BEHIND_IN;
        lutSpeed = lut.ticksPerSec(distance);
        // How far round to the side the robot is from straight out of the mouth. The cell is a
        // box open at one end: from too far round, the shot hits its walls.
        offAxis = Math.atan2(Math.abs(dx), -dy * target.facesY);
    }

    /** No odometry this loop: nothing is valid. */
    public void noPose() { havePose = false; turn = 0; }

    // ---- Getters ----

    /** Turn input for drivetrain.drive(x, rx, y), like the right stick X. */
    public double turnCommand() { return havePose ? turn : 0; }

    public boolean hasPose() { return havePose; }

    /** Pointed at the target closely enough to shoot. */
    public boolean isAimed() {
        return havePose && Math.abs(headingError) <= Math.toRadians(Constants.AIM_TOLERANCE_DEG);
    }

    /**
     * A shot from here can go in: the LUT has a speed for this distance, and the robot is
     * within AIM_MAX_OFF_AXIS_DEG of straight out of the cell's open end.
     */
    public boolean inRange() {
        return havePose && lut.inRange(distance) && Math.toDegrees(offAxis) <= Constants.AIM_MAX_OFF_AXIS_DEG;
    }

    /** Degrees round from straight out of the mouth (0 = dead in front of the opening). */
    public double offAxisDeg() { return Math.toDegrees(offAxis); }

    /** Aimed, in range: firing now should score (once the flywheel is at the LUT speed). */
    public boolean shotReady() { return isAimed() && inRange(); }

    public double lutTicksPerSec() { return lutSpeed; }
    public double distanceInches() { return distance; }
    public double headingErrorDeg() { return Math.toDegrees(headingError); }

    // ---- Logging ----

    /** Alea/Aim/... : target, distance, heading error, turn command, LUT speed, ready flags. */
    public void log() {
        Logger.recordOutput("Alea/Aim/Target", target.name());
        Logger.recordOutput("Alea/Aim/HasPose", havePose);
        Logger.recordOutput("Alea/Aim/DistanceIn", distance);
        Logger.recordOutput("Alea/Aim/OffAxisDeg", Math.toDegrees(offAxis));
        Logger.recordOutput("Alea/Aim/TargetHeadingDeg", Math.toDegrees(targetHeading));
        Logger.recordOutput("Alea/Aim/HeadingErrorDeg", Math.toDegrees(headingError));
        Logger.recordOutput("Alea/Aim/TurnCommand", turnCommand());
        Logger.recordOutput("Alea/Aim/LutTicksPerSec", lutSpeed);
        Logger.recordOutput("Alea/Aim/Aimed", isAimed());
        Logger.recordOutput("Alea/Aim/InRange", inRange());
    }

    // ---- Helpers ----

    private static double wrap(double a) {
        while (a > Math.PI) a -= 2 * Math.PI;
        while (a < -Math.PI) a += 2 * Math.PI;
        return a;
    }
}
