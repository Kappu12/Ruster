// Rustmatics's local Carbon/Oxide companion. GPL-3.0-or-later.
// Installation appends PreviewProtocol.cs for Carbon's single-file compiler.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json;
using UnityEngine;
using Ruster.Preview;
namespace Oxide.Plugins
{
    [Info("RusterPreview", "Rustmatics", "0.3.7")]
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
        readonly Dictionary<ulong,Placement> mapOnly=new Dictionary<ulong,Placement>();
        Dictionary<ulong,Placement> current=new Dictionary<ulong,Placement>();
        readonly Dictionary<uint,bool> templateKinds=new Dictionary<uint,bool>();
        readonly Dictionary<uint,string> templatePaths=new Dictionary<uint,string>();
        sealed class EditTransaction
        {
            public Snapshot snapshot;public PlacementDelta delta;
            public readonly Dictionary<ulong,GameObject> staged=new Dictionary<ulong,GameObject>();
            public readonly List<TransformState> restored=new List<TransformState>();
            public readonly List<GameObject> retired=new List<GameObject>();
            public bool committed;
            public Dictionary<ulong,GameObject> next;
        }
        EditTransaction edit;EditPump pump;Snapshot waiting;bool editScheduled;double nextProgress;
        string directory; SessionConfig config;
        long revision,attemptedStamp; double nextHeartbeat; bool initialized;
        GameObject previewSpawn;int previousDeveloper;bool diagnostics;int removedPreloadHarbors;
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
                if(string.IsNullOrWhiteSpace(directory)||!Active())throw new Exception("No active Rustmatics-owned preview session");
                if(ConVar.Server.ip!="127.0.0.1"||Network.Net.sv.secure)throw new Exception("Preview requires a loopback-only insecure server");
                config=JsonConvert.DeserializeObject<SessionConfig>(ReadText(Path.Combine(directory,"config.json"),4096));
                if(config==null||config.url!=World.Url||config.token==null||config.token.Length!=64)throw new Exception("Preview map URL or session identity does not match");
                previousDeveloper=ConVar.Global.developer;ConVar.Global.developer=Math.Max(1,previousDeveloper);diagnostics=true;
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
                    if(MapOnly(obj)||TemplateMapOnly(p))mapOnly.Add(p.key,p);
                    current.Add(p.key,p);
                }
                if(!Active())return;
                // Claim only after the entire initial scene has matched.
                foreach(var entry in claimed)objects.Add(entry.Key,entry.Value);
                // Map-only records already caused Rust to load their asset
                // scenes. Remove the distant server instances before players
                // join; keep the asset-scene templates available for live edits.
                HashSet<GameObject> preload;
                if(World.SpawnedPrefabs.TryGetValue("RusterPreviewWarmup",out preload))
                {
                    var preloadCount=preload.Count;
                    foreach(var obj in preload.ToArray())Destroy(obj);
                    World.SpawnedPrefabs.Remove("RusterPreviewWarmup");
                    Puts("Preloaded "+preloadCount+" prefab packs; removed hidden server markers.");
                }
                ClearDetachedWarmups();InstallPreviewSpawn();
                timer.Once(.1f,ClearDetachedWarmups);timer.Once(2f,ClearDetachedWarmups);
                if(!string.IsNullOrEmpty(config.owner)&&config.owner.Length==17&&config.owner.All(c=>c>='0'&&c<='9'))
                    ConsoleSystem.Run(ConsoleSystem.Option.Server,"ownerid "+config.owner+" \"Rustmatics preview owner\"");
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
            var now=(DateTime.UtcNow-new DateTime(1970,1,1)).TotalSeconds;
            try
            {
                if(!Active()){Cleanup();return;}
                if(Network.Net.sv.secure||ConVar.Server.ip!="127.0.0.1"||config.url!=World.Url)
                {Write("server.blocked","Preview requires inactive EAC, loopback networking and the owned map.");Cleanup();return;}
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
                // The final physics step can consume the slice after it has
                // written READY. A later progress tick must not overwrite it.
                if(pump!=null&&edit.snapshot.revision>revision&&now>=nextProgress)
                {Write("server.status","UPDATING\nApplying scene revision "+edit.snapshot.revision+"; "+pump.Completed+" queued steps finished");nextProgress=now+.25;}
                if(stamp==attemptedStamp)return;
                attemptedStamp=stamp;
                var snapshot=Snapshot.Read(path);
                if(snapshot.revision>revision)
                {
                    if(pump==null)Apply(snapshot);
                    else if(snapshot.revision>edit.snapshot.revision&&(waiting==null||snapshot.revision>waiting.revision))waiting=snapshot;
                }
            }
            catch(Exception error){Write("server.status","ERROR\n"+error.Message);}
        }
        void OnPlayerDisconnected(BasePlayer player,string reason)
        {if(!string.IsNullOrWhiteSpace(directory)){Delete("client.connected");Write("client.disconnect",JsonConvert.SerializeObject(new{timestamp=DateTime.UtcNow.ToString("o"),reason}));}}
        static bool WarmupPosition(Vector3 p)
        {return p.x>=9000&&p.y<=-5000&&p.z>=9000&&p.z<=11000;}
        static bool IsAuthored(Transform node,HashSet<Transform> authoredRoots)
        {
            for(var parent=node;parent!=null;parent=parent.parent)
                if(authoredRoots.Contains(parent))return true;
            return false;
        }
        void ClearDetachedWarmups()
        {
            if(string.IsNullOrWhiteSpace(directory)||!Active()||Network.Net.sv.secure||config.url!=World.Url)return;
            var protectedRoots=new HashSet<Transform>(objects.Values.Where(o=>o!=null).Select(o=>o.transform));
            var retired=new HashSet<GameObject>();
            // Native monument scripts can detach children during Awake. They
            // are outside the marker hierarchy but remain in its reserved
            // distant underground area, still running invokes and spawners.
            foreach(var behaviour in UnityEngine.Object.FindObjectsByType<MonoBehaviour>(FindObjectsInactive.Exclude,FindObjectsSortMode.None))
            {
                if(behaviour==null||!behaviour.gameObject.scene.IsValid()||!WarmupPosition(behaviour.transform.position))continue;
                var node=behaviour.transform;
                if(IsAuthored(node,protectedRoots)||behaviour.GetComponentInParent<BasePlayer>()!=null)continue;
                while(node.parent!=null&&WarmupPosition(node.parent.position))node=node.parent;
                retired.Add(node.gameObject);
            }
            foreach(var obj in retired)Destroy(obj);
            if(retired.Count>0)Puts("Removed "+retired.Count+" detached preload roots and their scheduled callbacks.");
            PrunePreloadHarbors(protectedRoots);
        }
        void PrunePreloadHarbors(HashSet<Transform> authoredRoots)
        {
            // Harbor Awake registers paths in a static list. Destroying its
            // preload hierarchy does not unregister them. PlayerInit reads
            // that list before OnPlayerConnected and a dead path kicks the
            // first player as "Invalid Packet: Client Ready".
            const BindingFlags staticFields=BindingFlags.Static|BindingFlags.NonPublic|BindingFlags.Public;
            const BindingFlags instanceFields=BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public;
            var registry=typeof(CargoShip).GetField("harbors",staticFields);
            var calculated=typeof(CargoShip).GetField("hasCalculatedApproaches",staticFields);
            var cache=typeof(BasePlayer).GetField("cachedOceanPaths",staticFields);
            var oceanField=typeof(TerrainPath).GetField("OceanPatrolFar",instanceFields);
            if(registry==null || !registry.FieldType.IsGenericType || registry.FieldType.GetGenericTypeDefinition()!=typeof(List<>)
                || calculated?.FieldType!=typeof(bool) || calculated.IsInitOnly
                || cache?.FieldType!=typeof(ProtoBuf.OceanPaths) || cache.IsInitOnly
                || oceanField?.FieldType!=typeof(List<Vector3>))
                throw new Exception("This Rust build does not expose the expected cargo route registry");
            var entryType=registry.FieldType.GetGenericArguments()[0];
            var pathField=entryType.GetField("harborPath",instanceFields);
            var transformField=entryType.GetField("harborTransform",instanceFields);
            if(pathField?.FieldType!=typeof(BasePath) || transformField?.FieldType!=typeof(Transform))
                throw new Exception("Unexpected native harbor registration layout");
            var entries=registry.GetValue(null) as IList;
            if(entries==null || entries.IsReadOnly)throw new Exception("Native harbor registrations are unavailable");
            int removed=0;
            for(int i=entries.Count-1;i>=0;i--)
            {
                var entry=entries[i];
                var path=pathField.GetValue(entry) as BasePath;
                var harbor=transformField.GetValue(entry) as Transform;
                bool valid=path!=null && harbor!=null && path.gameObject.scene.IsValid()
                    && path.nodes!=null && path.nodes.Count>0 && path.nodes.All(node=>node!=null);
                if(valid && (!WarmupPosition(harbor.position) || IsAuthored(harbor,authoredRoots)))continue;
                entries.RemoveAt(i);
                removed++;
            }
            if(removed>0)
            {
                removedPreloadHarbors+=removed;
                calculated.SetValue(null,false);
                // A failed PlayerInit can leave a partially populated cache.
                // Drop its reference; it aliases native terrain-owned lists.
                cache.SetValue(null,null);
                Puts("Removed "+removed+" invalid preload harbor registrations.");
            }
            var ocean=TerrainMeta.Path==null?null:oceanField.GetValue(TerrainMeta.Path) as List<Vector3>;
            int validated=0;
            if(ocean!=null&&ocean.Count>0)
                for(int i=0;i<CargoShip.TotalAvailableHarborDockingPaths;i++)
                {
                    var route=CargoShip.GetCargoApproachPath(i);
                    if(route==null||route.Count==0)throw new Exception("Native cargo route validation failed");
                    validated++;
                }
            Write("server.routes",JsonConvert.SerializeObject(new{
                removedPreloadHarbors,retainedHarbors=entries.Count,oceanRoutePoints=ocean?.Count??0,
                validatedCargoRoutes=validated,nativeRouteResolutionPassed=validated==entries.Count}));
        }
        void InstallPreviewSpawn()
        {
            var manager=ServerMgr.Instance;if(manager==null)throw new Exception("Preview spawn manager is unavailable");
            // Carbon can publicize server fields; support both visibilities
            // while still requiring the exact verified name and array type.
            var flags=System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Public;
            var fields=new[]{typeof(ServerMgr).GetField("proceduralSpawnPoints",flags),typeof(ServerMgr).GetField("fallbackProceduralSpawnPoints",flags)};
            if(fields.Any(f=>f==null||f.FieldType!=typeof(GameObject[])||f.IsInitOnly))throw new Exception("This Rust build does not expose the expected spawn caches");
            // FindSpawnPoint runs before OnPlayerRespawn for a first-time
            // connection. Marker destruction can leave dead entries in its
            // cached tag arrays, so give both caches a live owned fallback.
            previewSpawn=new GameObject("RusterPreviewSpawn");previewSpawn.tag="spawnpoint";
            float height=TerrainMeta.HeightMap==null?1f:TerrainMeta.HeightMap.GetHeight(Vector3.zero)+1f;
            previewSpawn.transform.position=new Vector3(0,height,0);
            foreach(var field in fields)field.SetValue(manager,new[]{previewSpawn});
            Write("server.spawn",JsonConvert.SerializeObject(new{source="Owned preview fallback",position=new[]{0f,height,0f},nativeSpawnCachesRefreshed=true}));
        }
        object OnPlayerRespawn(BasePlayer player,BasePlayer.SpawnPoint original)
        {
            if(!initialized||!Active()||player==null||player.net==null||player.net.connection==null)return null;
            var address=player.net.connection.ipaddress;
            if(address!="127.0.0.1"&&!address.StartsWith("127.0.0.1:",StringComparison.Ordinal))return null;
            // Native-ground previews have a walkable surface. Do not spawn
            // above the tallest canopy and inflict fall damage on entry.
            if(TerrainMeta.AlphaMap!=null&&TerrainMeta.HeightMap!=null&&TerrainMeta.AlphaMap.GetAlpha(Vector3.zero)>.5f)
                return new BasePlayer.SpawnPoint{pos=new Vector3(0,TerrainMeta.HeightMap.GetHeight(Vector3.zero)+1f,0),rot=Quaternion.identity};
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
        static bool MapOnly(GameObject obj)
        {
            // These native scripts move children outside the root's ownership,
            // or require Rust's map initialization pass to spawn their entities.
            // A root transform/destroy is not a complete monument transaction.
            return obj!=null&&(obj.GetComponentInChildren<DetachMonumentChildren>(true)!=null||
                obj.GetComponentsInChildren<SceneToPrefabSpawner>(true).Any(s=>s.EntitiesToSpawn.Count>0));
        }
        static void Transform(GameObject obj,Placement p)
        {
            obj.transform.SetPositionAndRotation(Vector(p.position),Rotation(p));obj.transform.localScale=Vector(p.scale);
            foreach(var entity in obj.GetComponentsInChildren<BaseEntity>(true))
            {entity.networkEntityScale=true;entity.UpdateNetworkGroup();entity.SendNetworkUpdateImmediate();}
        }
        bool TemplateMapOnly(Placement p)
        {
            string known;bool kind;
            if(templatePaths.TryGetValue(p.uid,out known)&&known==p.path&&templateKinds.TryGetValue(p.uid,out kind))return kind;
            var prefab=GameManager.server.FindPrefab(p.path);
            if(StringPool.Get(p.uid)!=p.path||prefab==null)throw new Exception("Rust cannot load "+p.path+"; restart preview with this asset in the initial map");
            kind=MapOnly(prefab);templateKinds[p.uid]=kind;templatePaths[p.uid]=p.path;return kind;
        }
        void Apply(Snapshot snapshot)
        {
            edit=new EditTransaction{snapshot=snapshot,delta=new PlacementDelta(current,snapshot,mapOnly),next=new Dictionary<ulong,GameObject>(objects)};
            var transaction=edit;pump=new EditPump(ApplySteps(transaction).GetEnumerator(),()=>RollbackSteps(transaction).GetEnumerator());
            ScheduleEdit();
        }
        IEnumerable<EditStep> ApplySteps(EditTransaction job)
        {
            foreach(var p in job.delta.changed)yield return new EditStep(()=>{
                if(!mapOnly.ContainsKey(p.key)&&TemplateMapOnly(p))throw new Exception("Compound monument requires map initialization: "+p.path+
                    ". Add it to the saved composition before starting preview, or export a map and reload it.");
            });
            foreach(var p in job.delta.changed)
            {
                GameObject existing;Placement old;
                if(objects.TryGetValue(p.key,out existing)&&existing!=null&&current.TryGetValue(p.key,out old)&&old.uid==p.uid&&old.path==p.path)continue;
                yield return new EditStep(()=>{
                    var obj=GameManager.server.CreatePrefab(p.path,Vector(p.position),Rotation(p),Vector(p.scale));
                    if(obj==null)throw new Exception("Rust cannot create "+p.path);
                    job.staged.Add(p.key,obj);job.next[p.key]=obj;
                    foreach(var entity in obj.GetComponentsInChildren<BaseEntity>(true)){entity.enableSaving=false;if(entity.net==null)entity.Spawn();}
                    Transform(obj,p);
                },true);
            }
            foreach(var p in job.delta.changed)
            {
                if(job.staged.ContainsKey(p.key))continue;
                yield return new EditStep(()=>{var obj=job.next[p.key];job.restored.Add(new TransformState(obj));Transform(obj,p);},true);
            }
            yield return new EditStep(()=>Physics.SyncTransforms(),true);
            foreach(var key in job.delta.removed)job.next.Remove(key);
            // All potentially failing creations/setters have succeeded. Old
            // collider roots retire in small batches, before the acknowledgement.
            foreach(var entry in objects)
            {
                GameObject next;
                if(job.next.TryGetValue(entry.Key,out next)&&next==entry.Value)continue;
                job.retired.Add(entry.Value);
            }
            yield return new EditStep(()=>{
                objects.Clear();foreach(var entry in job.next)objects.Add(entry.Key,entry.Value);
                current=job.delta.target;job.committed=true;
            });
            foreach(var obj in job.retired){var retired=obj;yield return new EditStep(()=>Destroy(retired),true);}
            yield return new EditStep(()=>{
                Physics.SyncTransforms();revision=job.snapshot.revision;
                Write("server.revision",revision.ToString(System.Globalization.CultureInfo.InvariantCulture));
                Write("server.status","READY\nServer scene revision "+revision+" ("+objects.Count+" placements)");
            },true);
        }
        IEnumerable<EditStep> RollbackSteps(EditTransaction job)
        {
            if(job.committed)
            {
                // Destructive retirement has started: preserve ownership of
                // the new scene and finish old-root cleanup, without claiming
                // the failed revision was acknowledged successfully.
                foreach(var obj in job.retired){var value=obj;yield return new EditStep(()=>Destroy(value),true);}
                yield break;
            }
            for(int i=job.restored.Count-1;i>=0;i--){var state=job.restored[i];yield return new EditStep(()=>{
                state.Restore();if(state.obj!=null)foreach(var entity in state.obj.GetComponentsInChildren<BaseEntity>(true))
                {entity.UpdateNetworkGroup();entity.SendNetworkUpdateImmediate();}
            },true);}
            foreach(var obj in job.staged.Values){var value=obj;yield return new EditStep(()=>Destroy(value),true);}
            yield return new EditStep(()=>Physics.SyncTransforms(),true);
        }
        void ScheduleEdit()
        {
            if(editScheduled||pump==null)return;editScheduled=true;timer.Once(.02f,AdvanceEdit);
        }
        void AdvanceEdit()
        {
            editScheduled=false;if(!initialized||pump==null)return;
            if(!Active()){Cleanup();return;}
            if(Network.Net.sv.secure||ConVar.Server.ip!="127.0.0.1"||config.url!=World.Url)
            {Write("server.blocked","Preview session verification failed during a queued edit.");Cleanup();return;}
            pump.Advance();
            if(pump.Done)
            {
                if(pump.Error!=null)Write("server.status","ERROR\n"+pump.Error.Message);
                pump.Dispose();pump=null;edit=null;
                var latest=waiting;waiting=null;
                if(latest!=null&&latest.revision>revision)try{Apply(latest);}catch(Exception error){Write("server.status","ERROR\n"+error.Message);}
            }
            ScheduleEdit();
        }
        void Destroy(GameObject obj)
        {
            if(obj==null)return;
            try
            {
                // Destroy is deferred. Disable physics/trigger participation now,
                // before advertising this snapshot as applied.
                obj.SetActive(false);
                // Monument warmups schedule native callbacks on non-entity
                // components too. Remove them before their transforms die.
                var callbacks=new HashSet<Behaviour>(obj.GetComponentsInChildren<Behaviour>(true));
                if(InvokeHandler.Instance!=null)InvokeHandler.Instance.CancelInvokes(callbacks);
                foreach(var behaviour in obj.GetComponentsInChildren<MonoBehaviour>(true))
                    if(behaviour!=null)behaviour.CancelInvoke();
                foreach(var entity in obj.GetComponentsInChildren<BaseEntity>(true))
                    if(entity!=null&&!entity.IsDestroyed)try{entity.Kill();}catch(Exception error){PrintError(error.Message);}
            }
            finally{if(obj!=null)UnityEngine.Object.Destroy(obj);}
        }
        void Cleanup()
        {
            initialized=false;
            if(diagnostics){ConVar.Global.developer=previousDeveloper;diagnostics=false;}
            if(pump!=null)pump.Dispose();pump=null;waiting=null;
            if(!string.IsNullOrWhiteSpace(directory)){Delete("server.ready");Delete("client.connected");}
            var owned=new HashSet<GameObject>(objects.Values);if(edit!=null){foreach(var obj in edit.staged.Values)owned.Add(obj);foreach(var obj in edit.retired)owned.Add(obj);}edit=null;
            foreach(var obj in owned)Destroy(obj);objects.Clear();mapOnly.Clear();current.Clear();templateKinds.Clear();templatePaths.Clear();
            if(previewSpawn!=null)UnityEngine.Object.Destroy(previewSpawn);previewSpawn=null;
            Physics.SyncTransforms();
        }
        void Unload(){Cleanup();}
    }
}
