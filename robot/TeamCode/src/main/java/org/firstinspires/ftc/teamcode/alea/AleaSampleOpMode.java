package org.firstinspires.ftc.teamcode.alea;

import com.qualcomm.hardware.gobilda.GoBildaPinpointDriver;
import com.qualcomm.robotcore.eventloop.opmode.TeleOp;

import org.firstinspires.ftc.robotcore.external.navigation.AngleUnit;
import org.firstinspires.ftc.robotcore.external.navigation.DistanceUnit;
import org.firstinspires.ftc.robotcore.external.navigation.Pose2D;
import org.firstinspires.ftc.robotcore.external.navigation.UnnormalizedAngleUnit;
import org.psilynx.psikit.core.Logger;
import org.psilynx.psikit.ftc.FtcLogTuning;
import org.psilynx.psikit.ftc.PsiKitIterativeOpMode;

/**
 * The smallest OpMode that logs what ALEA reads (docs/robot-interface.md).
 * PsiKitIterativeOpMode starts and ends the PsiKit session; this class only
 *  1. sets the logging options and records the constants as metadata, and
 *  2. feeds the Pinpoint pose to AimAssist each loop and calls aim.log().
 * It does not drive anything. Copy the pattern into your own OpMode.
 */
@TeleOp(name = "ALEA Sample", group = "ALEA")
public class AleaSampleOpMode extends PsiKitIterativeOpMode {
    private AimAssist aim;
    private GoBildaPinpointDriver pinpoint;
    private boolean dpadUpWasDown = false;

    @Override
    protected void onPsiKitInit() {
        // Hardware must be fetched after PsiKit starts: the hardware map is PsiKit's wrapper.
        pinpoint = hardwareMap.get(GoBildaPinpointDriver.class, Constants.PINPOINT_NAME);
        pinpoint.setPosition(new Pose2D(
                DistanceUnit.INCH, Constants.START_X_IN, Constants.START_Y_IN,
                AngleUnit.DEGREES,
                Constants.START_HEADING_DEG));
        aim = new AimAssist(LaunchLut.standard(),
                Constants.START_TARGET_RED ? AimAssist.Target.RED_AUDIENCE : AimAssist.Target.BLUE_AUDIENCE);
    }

    @Override
    protected void onPsiKitConfigureLogging() {
        // Motor current is a slow non-bulk read, so it is off unless asked for. It is only
        // logged outside the bulk-only profile.
        FtcLogTuning.bulkOnlyLogging = false;
        FtcLogTuning.logMotorCurrent = true;

        Logger.recordMetadata("Alea/Meta/ContractVersion", "1");
        Logger.recordMetadata("Alea/Meta/RedHiveXIn", String.valueOf(Constants.RED_HIVE_X_IN));
        Logger.recordMetadata("Alea/Meta/BlueHiveXIn", String.valueOf(Constants.BLUE_HIVE_X_IN));
        Logger.recordMetadata("Alea/Meta/HiveAudienceMouthYIn", String.valueOf(Constants.HIVE_AUDIENCE_MOUTH_Y_IN));
        Logger.recordMetadata("Alea/Meta/HiveRearMouthYIn", String.valueOf(Constants.HIVE_REAR_MOUTH_Y_IN));
        Logger.recordMetadata("Alea/Meta/LaunchAngleDeg", String.valueOf(Constants.LAUNCH_ANGLE_DEG));
        Logger.recordMetadata("Alea/Meta/LauncherExitBehindIn", String.valueOf(Constants.LAUNCHER_EXIT_BEHIND_IN));
        Logger.recordMetadata("Alea/Meta/LauncherMaxTicksPerSec", String.valueOf(Constants.LAUNCHER_MAX_TICKS_PER_SEC));
    }

    @Override
    protected void onPsiKitLoop() {
        // dpad up: the hive tipped, aim at its other cell (once per press).
        if (gamepad1.dpad_up && !dpadUpWasDown) {
            aim.flipRaisedCell();
        }
        dpadUpWasDown = gamepad1.dpad_up;
        pinpoint.update();
        aim.update(
                pinpoint.getPosX(DistanceUnit.INCH),
                pinpoint.getPosY(DistanceUnit.INCH),
                pinpoint.getHeading(AngleUnit.RADIANS),
                pinpoint.getHeadingVelocity(UnnormalizedAngleUnit.RADIANS));
        aim.log();
    }
}
