// Ruster's local Carbon/Oxide companion. GPL-3.0-or-later.
// Installation appends PreviewProtocol.cs for Carbon's single-file compiler.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using UnityEngine;
using Ruster.Preview;
namespace Oxide.Plugins
{
    [Info("RusterPreview", "Ruster", "0.3.0")]
    [Description("Applies editor placements only inside an owned loopback preview session")]
    public class RusterPreview : RustPlugin
    {
        class SessionConfig { public string owner; public string url; public string token; }
        class Command { public string command; }
        struct TransformState
        {
            public GameObject obj; public Vector3 position, scale; public Quaternion rotation;
            public TransformState(GameObject value)
            { obj=value; position=value.transform.position; rotation=value.transform.rotation; scale=value.transform.localScale; }
            public void Restore() { if(obj!=null) { obj.transform.SetPositionAndRotation(position,rotation); obj.transform.localScale=scale; } }
        }
        readonly Dictionary<ulong,GameObject> objects=new Dictionary<ulong,GameObject>();
        string directory; SessionConfig config;
        long revision,attemptedStamp; double nextHeartbeat; bool initialized;
        bool Active() { return File.Exists(Path.Combine(directory,"active.flag"))&&!File.Exists(Path.Combine(directory,"stop.flag")); }
        static string ReadText(string path,long maximum)
        {
            using(var input=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete))
            {
                if(input.Length>maximum)throw new IOException("Preview file exceeds size limit");
                using(var reader=new StreamReader(input))return reader.ReadToEnd();
            }
        }
        void Write(string name,string value)
        {WriteBytes(name,new System.Text.UTF8Encoding(false).GetBytes(value));}
        void WriteBytes(string name,byte[] value)
        {
            var path=Path.Combine(directory,name); var temporary=path+".server.tmp";
            File.WriteAllBytes(temporary,value);
            if(File.Exists(path))File.Replace(temporary,path,null); else File.Move(temporary,path);
        }
        void Delete(string name) { try { File.Delete(Path.Combine(directory,name)); } catch(IOException){} }
        void OnServerInitialized()
        {
            directory=Environment.GetEnvironmentVariable("RUSTER_PREVIEW_DIR");
            try
            {
                if(string.IsNullOrWhiteSpace(directory)||!Active())throw new Exception("No active Ruster-owned preview session");
                if(ConVar.Server.ip!="127.0.0.1"||Network.Net.sv.secure)throw new Exception("Preview requires a loopback-only insecure server");
                config=JsonConvert.DeserializeObject<SessionConfig>(ReadText(Path.Combine(directory,"config.json"),4096));
                if(config==null||config.url!=World.Url||config.token==null||config.token.Length!=64)throw new Exception("Preview map URL or session identity does not match");
                // env.oceanlevel is a native replicated variable. Move the ocean
                // out of view for this owned session; alpha holes hide terrain.
                ConVar.Env.oceanlevel=-1000000f;
                var initial=Snapshot.Read(Path.Combine(directory,"initial.bin"));
                HashSet<GameObject> baked;
                var candidates=World.SpawnedPrefabs.TryGetValue("RusterPreview",out baked)?new List<GameObject>(baked):new List<GameObject>();
                var claimed=new Dictionary<ulong,GameObject>();
                foreach(var p in initial.placements)
                {
                    if(StringPool.Get(p.uid)!=p.path)throw new Exception("Invalid initial prefab reference");
                    var position=Vector(p.position);
                    var obj=candidates.FirstOrDefault(o=>o!=null&&o.name==p.path&&(o.transform.position-position).sqrMagnitude<0.0001f);
                    if(obj==null)throw new Exception("Cannot claim initial map placement "+p.path);
                    candidates.Remove(obj);claimed.Add(p.key,obj);
                }
                if(!Active())return;
                // Claim only after the entire initial scene has matched.
                foreach(var entry in claimed)objects.Add(entry.Key,entry.Value);
                if(!string.IsNullOrEmpty(config.owner)&&config.owner.Length==17&&config.owner.All(c=>c>='0'&&c<='9'))
                    ConsoleSystem.Run(ConsoleSystem.Option.Server,"ownerid "+config.owner+" \"Ruster preview owner\"");
                initialized=true;Tick();timer.Every(0.25f,Tick);
                Puts("Local preview bridge ready. Rust client preview requires explicit no-EAC injection.");
            }
            catch(Exception error)
            {
                PrintError(error.Message);
                if(!string.IsNullOrWhiteSpace(directory)){Write("server.blocked",error.Message);Cleanup();}
            }
        }
        void Tick()
        {
            if(!initialized)return;
            try
            {
                if(!Active()){Cleanup();return;}
                if(Network.Net.sv.secure||ConVar.Server.ip!="127.0.0.1"||config.url!=World.Url)
                {Write("server.blocked","Preview requires inactive EAC, loopback networking and the owned map.");Cleanup();return;}
                var now=(DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds;
                if(now>=nextHeartbeat)
                {
                    Write("server.ready",JsonConvert.SerializeObject(new{protocol=1,client_protocol=2,secure=Network.Net.sv.secure,ip=ConVar.Server.ip,timestamp=now,pid=Process.GetCurrentProcess().Id,token=config.token}));
                    nextHeartbeat=now+1;
                }
                // The client verifies this observed peer port belongs to its own
                // process. No obfuscated client World/GameManager fields needed.
                var peers=BasePlayer.activePlayerList.Where(p=>p!=null&&p.IsConnected&&p.net!=null&&p.net.connection!=null).ToArray();
                var endpoint=peers.Length==1?peers[0].net.connection.ipaddress:null;uint port;
                if(endpoint!=null&&endpoint.StartsWith("127.0.0.1:",StringComparison.Ordinal)
                    &&uint.TryParse(endpoint.Substring(10),System.Globalization.NumberStyles.None,System.Globalization.CultureInfo.InvariantCulture,out port)&&port>0&&port<=65535)
                    WriteBytes("client.connected",PeerProof.Encode(config.token,(uint)Process.GetCurrentProcess().Id,port,(long)(now*1000),config.url));
                else Delete("client.connected");
            }
            catch(Exception error){PrintError("Preview heartbeat failed: "+error.Message);return;}
            // Console remains usable when a scene update fails.
            Commands();
            try
            {
                var path=Path.Combine(directory,"scene.bin");var stamp=File.GetLastWriteTimeUtc(path).Ticks;
                if(stamp==attemptedStamp)return;
                attemptedStamp=stamp;
                var snapshot=Snapshot.Read(path);
                if(snapshot.revision>revision)Apply(snapshot);
            }
            catch(Exception error){Write("server.status","ERROR\n"+error.Message);}
        }
        void OnPlayerDisconnected(BasePlayer player,string reason)
        {if(!string.IsNullOrWhiteSpace(directory))Delete("client.connected");}
        object OnPlayerRespawn(BasePlayer player,BasePlayer.SpawnPoint original)
        {
            if(!initialized||!Active()||player==null||player.net==null||player.net.connection==null)return null;
            var address=player.net.connection.ipaddress;
            if(address!="127.0.0.1"&&!address.StartsWith("127.0.0.1:",StringComparison.Ordinal))return null;
            // Void maps have no beach spawn points. Spawn above the composition
            // without adding any platform or other geometry to the preview.
            var bounds=new Bounds(Vector3.zero,Vector3.zero);bool found=false;
            foreach(var obj in objects.Values)
            {
                if(obj==null)continue;
                foreach(var collider in obj.GetComponentsInChildren<Collider>(true))
                {
                    if(!collider.enabled||collider.isTrigger)continue;
                    if(!found){bounds=collider.bounds;found=true;}else bounds.Encapsulate(collider.bounds);
                }
            }
            return new BasePlayer.SpawnPoint{pos=new Vector3(bounds.center.x,(found?bounds.max.y:0)+3,bounds.center.z),rot=Quaternion.identity};
        }
        void Commands()
        {
            var queue=Path.Combine(directory,"commands");if(!Directory.Exists(queue))return;
            foreach(var file in Directory.GetFiles(queue,"*.json").OrderBy(p=>p,StringComparer.Ordinal).Take(8))
            {
                try
                {
                    var item=JsonConvert.DeserializeObject<Command>(ReadText(file,32768));File.Delete(file);
                    var command=item==null?null:item.command;
                    if(string.IsNullOrWhiteSpace(command)||command.Length>4096||command.IndexOfAny(new[]{'\n','\r','\0'})>=0)continue;
                    Puts("> "+command+"\n"+ConsoleSystem.Run(ConsoleSystem.Option.Server,command));
                }
                catch(Exception error){PrintError("Preview console: "+error.Message);try{File.Delete(file);}catch(IOException){}}
            }
        }
        static Vector3 Vector(float[] value){return new Vector3(value[0],value[1],value[2]);}
        static Quaternion Rotation(Placement p){return new Quaternion(p.rotation[0],p.rotation[1],p.rotation[2],p.rotation[3]);}
        static void Transform(GameObject obj,Placement p)
        {
            obj.transform.SetPositionAndRotation(Vector(p.position),Rotation(p));obj.transform.localScale=Vector(p.scale);
            foreach(var entity in obj.GetComponentsInChildren<BaseEntity>(true))
            {entity.networkEntityScale=true;entity.UpdateNetworkGroup();entity.SendNetworkUpdateImmediate();}
        }
        void Apply(Snapshot snapshot)
        {
            foreach(var p in snapshot.placements)
                if(StringPool.Get(p.uid)!=p.path||GameManager.server.FindPrefab(p.path)==null)throw new Exception("Rust cannot load "+p.path+"; restart preview with this asset in the initial map");
            var staged=new Dictionary<ulong,GameObject>();var restored=new List<TransformState>();var next=new Dictionary<ulong,GameObject>();
            try
            {
                foreach(var p in snapshot.placements)
                {
                    GameObject obj;
                    if(!objects.TryGetValue(p.key,out obj)||obj==null||obj.name!=p.path)
                    {
                        obj=GameManager.server.CreatePrefab(p.path,Vector(p.position),Rotation(p),Vector(p.scale));
                        if(obj==null)throw new Exception("Rust cannot create "+p.path);
                        staged.Add(p.key,obj);
                        foreach(var entity in obj.GetComponentsInChildren<BaseEntity>(true)){entity.enableSaving=false;if(entity.net==null)entity.Spawn();}
                        Transform(obj,p);
                    }
                    next.Add(p.key,obj);
                }
                foreach(var p in snapshot.placements)
                {
                    if(staged.ContainsKey(p.key))continue;
                    var obj=next[p.key];
                    if(obj.transform.position==Vector(p.position)&&obj.transform.rotation==Rotation(p)&&obj.transform.localScale==Vector(p.scale))continue;
                    restored.Add(new TransformState(obj));Transform(obj,p);
                }
                Physics.SyncTransforms();
            }
            catch
            {
                foreach(var state in restored)try
                {
                    state.Restore();
                    if(state.obj!=null)foreach(var entity in state.obj.GetComponentsInChildren<BaseEntity>(true))
                    {entity.UpdateNetworkGroup();entity.SendNetworkUpdateImmediate();}
                }
                catch(Exception error){PrintError("Preview transform rollback: "+error.Message);}
                foreach(var obj in staged.Values)Destroy(obj);
                try{Physics.SyncTransforms();}catch(Exception error){PrintError(error.Message);}
                throw;
            }
            var retired=objects.Where(e=>!next.ContainsKey(e.Key)||next[e.Key]!=e.Value).Select(e=>e.Value).ToArray();
            objects.Clear();foreach(var entry in next)objects.Add(entry.Key,entry.Value);
            foreach(var obj in retired)Destroy(obj);
            revision=snapshot.revision;
            Write("server.revision",revision.ToString(System.Globalization.CultureInfo.InvariantCulture));
            Write("server.status","READY\nServer scene revision "+revision+" ("+objects.Count+" placements)");
        }
        void Destroy(GameObject obj)
        {
            if(obj==null)return;
            try
            {
                foreach(var entity in obj.GetComponentsInChildren<BaseEntity>(true))
                    if(entity!=null&&!entity.IsDestroyed)try{entity.Kill();}catch(Exception error){PrintError(error.Message);}
            }
            finally{if(obj!=null)UnityEngine.Object.Destroy(obj);}
        }
        void Cleanup()
        {
            initialized=false;
            if(!string.IsNullOrWhiteSpace(directory)){Delete("server.ready");Delete("client.connected");}
            foreach(var obj in objects.Values)Destroy(obj);objects.Clear();
        }
        void Unload(){Cleanup();}
    }
}
