import org.firstinspires.ftc.teamcode.sim.biobuzz.*;
import org.firstinspires.ftc.teamcode.sim.Util.*;
import java.io.*;
import java.util.*;
/** Reference for the GPU kernel: one shot per input line "x y heading tps vx vy"; prints 0 miss, 1 red hive, 2 blue hive.
 *  args: pollenDiameter wallRestitution infile */
public class ShotDump { public static void main(String[] a) throws Exception {
  SimLauncherConfig lc=new SimLauncherConfig(); BioBuzzConfig c=new BioBuzzConfig();
  c.pollenDiameter=Double.parseDouble(a[0]); c.wallRestitution=Double.parseDouble(a[1]);
  BioBuzzField f=new BioBuzzField(c,new SimIntakeConfig(),lc);
  Hive red=f.hives.get(Alliance.RED), blue=f.hives.get(Alliance.BLUE);
  Ball shot=f.robotStorage.peekFirst(); for(Ball b:f.balls) if(b!=shot&&b.state==Ball.State.FREE) b.state=Ball.State.STAGED;
  BufferedReader br=new BufferedReader(new FileReader(a[2])); StringBuilder out=new StringBuilder(); String line;
  while((line=br.readLine())!=null){ String[] p=line.trim().split("\\s+"); if(p.length<6) continue;
    RobotInput in=new RobotInput(); in.x=Double.parseDouble(p[0]); in.y=Double.parseDouble(p[1]); in.heading=Double.parseDouble(p[2]);
    double tps=Double.parseDouble(p[3]); in.vx=Double.parseDouble(p[4]); in.vy=Double.parseDouble(p[5]);
    shot.state=Ball.State.IN_ROBOT; red.upCell.remove(shot); blue.upCell.remove(shot); f.robotStorage.clear(); f.robotStorage.add(shot);
    f.step(0.002,in); f.launch(tps/28*2*Math.PI*1.89*0.45);
    for(int i=0;i<1000&&shot.state==Ball.State.FREE;i++){ f.step(0.002,in); if(shot.onFloor()) break; }
    f.drainEvents();
    int r=0; if(shot.state==Ball.State.IN_CELL) r= red.upCell.contains(shot)?1:2;
    red.upCell.remove(shot); blue.upCell.remove(shot);
    out.append(r).append('\n'); }
  System.out.print(out);
}}
