using System.IO;
using Guard.App;

var testRoot=Path.GetFullPath("artifacts/evidence/settings-test");
Directory.CreateDirectory(testRoot);
var path=Path.Combine(testRoot,"settings-"+Guid.NewGuid().ToString("N")+".json");
void Check(bool condition,string name) { if(!condition) throw new Exception(name); Console.WriteLine(name+" PASS"); }
var fresh=Settings.LoadFrom(path,out var warning);
Check(!fresh.DesiredProtectionEnabled && fresh.CloseToTray && warning==null,"defaults");
fresh.DesiredProtectionEnabled=true;fresh.CloseToTray=false;fresh.SaveTo(path);
var saved=Settings.LoadFrom(path,out warning);
Check(saved.DesiredProtectionEnabled && !saved.CloseToTray && warning==null,"roundtrip");
fresh.DesiredProtectionEnabled=false;fresh.SaveTo(path);
Check(File.Exists(path+".bak") && Settings.LoadFrom(path+".bak",out warning).DesiredProtectionEnabled,"atomic-backup");
File.WriteAllText(path,"{broken");
var recovered=Settings.LoadFrom(path,out warning);
Check(!recovered.DesiredProtectionEnabled && warning!=null && Directory.GetFiles(testRoot,Path.GetFileName(path)+".invalid-*").Length==1,"corrupt-reset");
File.WriteAllText(path,"{\"schemaVersion\":99,\"desiredProtectionEnabled\":true}");
Check(!Settings.LoadFrom(path,out warning).DesiredProtectionEnabled && warning!=null,"unknown-schema");
try { fresh.SaveTo(Path.Combine(path,"blocked.json")); throw new Exception("Expected save failure"); }
catch(IOException) { Console.WriteLine("unwritable-path PASS"); }
Check(StartupRegistration.Owned("\"C:\\App\\WeixinVolumeGuard.exe\" --background") && !StartupRegistration.Owned("\"C:\\App\\Other.exe\" --background"),"startup-ownership");
