// Ruster's local Carbon/Oxide companion. GPL-3.0-or-later.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using UnityEngine;

namespace Oxide.Plugins
{
    [Info("RusterPreview", "Ruster", "0.1.0")]
    [Description("Applies editor placements only inside an owned loopback preview session")]
    public class RusterPreview : RustPlugin
    {
        class SessionConfig { public string owner; public string url; }
        class Snapshot { public long revision; public Placement[] placements; }
        class Placement { public ulong key; public uint uid; public string path; public float[] position; public float[] rotation; public float[] scale; }
        class Command { public string command; }
        readonly Dictionary<ulong, GameObject> objects = new Dictionary<ulong, GameObject>();
        string directory;
        long revision;
        bool initialized;

        void OnServerInitialized()
        {
            directory = Environment.GetEnvironmentVariable("RUSTER_PREVIEW_DIR");
            if (string.IsNullOrWhiteSpace(directory) || !File.Exists(Path.Combine(directory, "active.flag")))
            { PrintError("No active Ruster-owned preview session. Plugin disabled."); return; }
            if (ConVar.Server.ip != "127.0.0.1" || Network.Net.sv.secure)
            { PrintError("RusterPreview requires a loopback-only insecure server. Plugin disabled."); return; }
            var config = JsonConvert.DeserializeObject<SessionConfig>(File.ReadAllText(Path.Combine(directory, "config.json")));
            if (config.url != World.Url) { PrintError("Preview map URL does not match the owned session."); return; }
            if (!string.IsNullOrEmpty(config.owner) && config.owner.Length == 17 && config.owner.All(char.IsDigit))
                ConsoleSystem.Run(ConsoleSystem.Option.Server, "ownerid " + config.owner + " \"Ruster preview owner\"");
            var initial = JsonConvert.DeserializeObject<Snapshot>(File.ReadAllText(Path.Combine(directory, "initial.json")));
            HashSet<GameObject> baked;
            var candidates = World.SpawnedPrefabs.TryGetValue("RusterPreview", out baked)
                ? new List<GameObject>(baked) : new List<GameObject>();
            foreach (var p in initial.placements)
            {
                var position = Vector(p.position);
                var obj = candidates.FirstOrDefault(o => o != null && o.name == p.path && (o.transform.position - position).sqrMagnitude < 0.0001f);
                if (obj == null) { PrintError("Cannot claim initial map placement " + p.path + "; preview disabled to avoid duplicate objects."); return; }
                candidates.Remove(obj); objects[p.key] = obj;
            }
            initialized = true;
            File.WriteAllText(Path.Combine(directory, "server.ready"), "Ruster preview plugin ready");
            timer.Every(0.25f, Tick);
            Puts("Local preview bridge ready. Rust client preview requires explicit no-EAC injection.");
        }

        void Tick()
        {
            if (!initialized) return;
            if (!File.Exists(Path.Combine(directory, "active.flag"))) { Cleanup(); return; }
            try
            {
                var connected = Path.Combine(directory, "client.connected");
                if (BasePlayer.activePlayerList.Any(p => p != null && p.IsConnected && p.net != null && p.net.connection != null
                    && p.net.connection.ipaddress.StartsWith("127.0.0.1"))) File.WriteAllText(connected, "loopback player connected");
                else if (File.Exists(connected)) File.Delete(connected);
                var path = Path.Combine(directory, "scene.json");
                if (new FileInfo(path).Length > 16 * 1024 * 1024) throw new Exception("Snapshot exceeds size limit");
                var snapshot = JsonConvert.DeserializeObject<Snapshot>(File.ReadAllText(path));
                if (snapshot.revision != revision) Apply(snapshot);
                var queue = Path.Combine(directory, "commands");
                if (Directory.Exists(queue)) foreach (var commandFile in Directory.GetFiles(queue, "*.json").Take(8))
                {
                    if (new FileInfo(commandFile).Length > 32768) { File.Delete(commandFile); continue; }
                    var command = JsonConvert.DeserializeObject<Command>(File.ReadAllText(commandFile)).command;
                    File.Delete(commandFile);
                    if (string.IsNullOrWhiteSpace(command) || command.Length > 4096 || command.Contains("\n") || command.Contains("\r")) continue;
                    var response = ConsoleSystem.Run(ConsoleSystem.Option.Server, command);
                    Puts("> " + command + "\n" + response);
                }
            }
            catch (Exception error) { File.WriteAllText(Path.Combine(directory, "server.status"), "ERROR\n" + error.Message); }
        }

        static Vector3 Vector(float[] value) { if (value == null || value.Length != 3 || value.Any(v => float.IsNaN(v) || float.IsInfinity(v))) throw new Exception("Invalid preview vector"); return new Vector3(value[0], value[1], value[2]); }
        void Apply(Snapshot snapshot)
        {
            if (snapshot.placements == null || snapshot.placements.Length > 2000) throw new Exception("Invalid placement count");
            var keys = new HashSet<ulong>();
            foreach (var p in snapshot.placements)
            {
                if (!keys.Add(p.key) || p.key == 0 || p.uid == 0 || p.path == null || !p.path.StartsWith("assets/")
                    || !p.path.EndsWith(".prefab") || p.path.Contains("..") || p.path.Contains("\\")
                    || StringPool.Get(p.uid) != p.path) throw new Exception("Invalid original prefab reference");
                Vector(p.position); Vector(p.scale);
                if (p.rotation == null || p.rotation.Length != 4 || p.rotation.Any(v => float.IsNaN(v) || float.IsInfinity(v))) throw new Exception("Invalid rotation");
            }
            foreach (var key in objects.Keys.Where(k => !keys.Contains(k)).ToArray()) { Destroy(objects[key]); objects.Remove(key); }
            foreach (var p in snapshot.placements)
            {
                var position = Vector(p.position); var scale = Vector(p.scale);
                var rotation = new Quaternion(p.rotation[0], p.rotation[1], p.rotation[2], p.rotation[3]);
                GameObject obj;
                if (!objects.TryGetValue(p.key, out obj) || obj == null || obj.name != p.path)
                {
                    if (obj != null) Destroy(obj);
                    obj = GameManager.server.CreatePrefab(p.path, position, rotation, scale);
                    if (obj == null) throw new Exception("Rust cannot load " + p.path);
                    objects[p.key] = obj;
                    foreach (var entity in obj.GetComponentsInChildren<BaseEntity>(true))
                    {
                        entity.enableSaving = false;
                        if (entity.net == null) entity.Spawn();
                    }
                }
                obj.transform.SetPositionAndRotation(position, rotation); obj.transform.localScale = scale;
                foreach (var entity in obj.GetComponentsInChildren<BaseEntity>(true))
                { entity.networkEntityScale = true; entity.UpdateNetworkGroup(); entity.SendNetworkUpdateImmediate(); }
            }
            Physics.SyncTransforms();
            revision = snapshot.revision;
            File.WriteAllText(Path.Combine(directory, "server.status"), "READY\nServer scene revision " + revision + " (" + objects.Count + " placements)");
        }

        void Destroy(GameObject obj)
        {
            if (obj == null) return;
            foreach (var entity in obj.GetComponentsInChildren<BaseEntity>(true)) if (entity != null && !entity.IsDestroyed) entity.Kill();
            if (obj != null) UnityEngine.Object.Destroy(obj);
        }
        void Cleanup() { foreach (var obj in objects.Values) Destroy(obj); objects.Clear(); initialized = false; }
        void Unload() { Cleanup(); }
    }
}
