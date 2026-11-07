import org.firstinspires.ftc.teamcode.StarterBot.*;
import java.io.*;
/** Reference for the GPU study: the REAL robot code's aim math. Input lines "x y"; prints
 *  targetHeadingRad distance lutTicks inRange(0/1) offAxisDeg (robot heading set to the target heading). */
public class AimDump { public static void main(String[] a) throws Exception {
  aimAssist aim=new aimAssist(launchLUT.standard(), aimAssist.Target.RED_AUDIENCE);
  BufferedReader br=new BufferedReader(new FileReader(a[0])); String line; StringBuilder o=new StringBuilder();
  while((line=br.readLine())!=null){ String[] p=line.trim().split("\\s+"); double x=Double.parseDouble(p[0]), y=Double.parseDouble(p[1]);
    aim.update(x,y,0,0); double th=Math.toRadians(-aim.headingErrorDeg())*-1; // error = target - 0
    o.append(String.format("%.9f %.9f %.9f %d %.9f%n", th, aim.distanceInches(), aim.lutTicksPerSec(), aim.inRange()?1:0, aim.offAxisDeg())); }
  System.out.print(o);
}}
