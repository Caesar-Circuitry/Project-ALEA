package org.firstinspires.ftc.teamcode.alea;

/**
 * The launch look-up table: how far the launcher is from the hive cell it's shooting at,
 * and the flywheel speed that puts a pollen in from there. Between two rows the speed is
 * a straight line between them (linear interpolation). Outside the table there is no
 * known good speed, so inRange() is false and the robot won't fire on its own.
 *
 * Pure math: no hardware, so it can be tested on a laptop.
 */
public final class LaunchLut {
    private final double[] distance;   // inches, increasing
    private final double[] speed;      // flywheel ticks/s at that distance

    public LaunchLut(double[] distanceInches, double[] ticksPerSec) {
        if (distanceInches.length != ticksPerSec.length || distanceInches.length < 2)
            throw new IllegalArgumentException("LUT needs at least 2 rows, same length");
        for (int i = 1; i < distanceInches.length; i++)
            if (distanceInches[i] <= distanceInches[i - 1])
                throw new IllegalArgumentException("LUT distances must increase");
        this.distance = distanceInches.clone();
        this.speed = ticksPerSec.clone();
    }

    /** The table in Constants.java. */
    public static LaunchLut standard() {
        return new LaunchLut(Constants.LUT_DISTANCE_IN, Constants.LUT_TICKS_PER_SEC);
    }

    public boolean inRange(double distanceInches) {
        return distanceInches >= distance[0] && distanceInches <= distance[distance.length - 1];
    }

    /** Flywheel speed for this distance. Outside the table: the nearest end (for pre-spinning). */
    public double ticksPerSec(double distanceInches) {
        if (distanceInches <= distance[0]) return speed[0];
        int last = distance.length - 1;
        if (distanceInches >= distance[last]) return speed[last];
        int i = 1;
        while (distance[i] < distanceInches) i++;
        double t = (distanceInches - distance[i - 1]) / (distance[i] - distance[i - 1]);
        return speed[i - 1] + t * (speed[i] - speed[i - 1]);
    }

    public double minDistance() { return distance[0]; }
    public double maxDistance() { return distance[distance.length - 1]; }
}
