// Pure wire decoder; exercised without Unity or a Rust process.
namespace Ruster.Preview
{
    using System;
    using System.Collections.Generic;
    using System.IO;
    using System.Text;
    internal static class PeerProof
    {
        public static byte[] Encode(string token, uint serverPid, uint port, long timestamp, string url)
        {
            if (token == null || token.Length != 64 || serverPid == 0 || port == 0 || port > 65535 || timestamp <= 0
                || url == null || !url.StartsWith("http://127.0.0.1:", StringComparison.Ordinal))
                throw new InvalidDataException("Invalid local connection proof");
            var address = new UTF8Encoding(false, true).GetBytes(url);
            if (address.Length > 2048) throw new InvalidDataException("Invalid local map URL");
            using (var output = new MemoryStream())
            using (var writer = new BinaryWriter(output))
            {
                writer.Write(Encoding.ASCII.GetBytes("RUSPEER2"));
                for (int i = 0; i < 64; i += 2) writer.Write(Convert.ToByte(token.Substring(i, 2), 16));
                writer.Write(serverPid); writer.Write(port); writer.Write(timestamp);
                writer.Write((uint)address.Length); writer.Write(address);
                return output.ToArray();
            }
        }
    }
    internal sealed class Placement
    {
        public ulong key;
        public uint uid;
        public string path;
        public float[] position, rotation, scale;
        public bool SamePlacement(Placement other)
        {
            if(other==null||key!=other.key||uid!=other.uid||path!=other.path)return false;
            for(int i=0;i<3;i++)if(position[i]!=other.position[i]||scale[i]!=other.scale[i])return false;
            for(int i=0;i<4;i++)if(rotation[i]!=other.rotation[i])return false;
            return true;
        }
    }
    internal sealed class Snapshot
    {
        public long revision;
        public Placement[] placements;
        public static Snapshot Read(string path)
        {
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                if (input.Length < 20 || input.Length > 16 * 1024 * 1024) throw new InvalidDataException("Invalid preview snapshot size");
                using (var reader = new BinaryReader(input, new UTF8Encoding(false, true)))
                {
                    if (Encoding.ASCII.GetString(reader.ReadBytes(8)) != "RUSLIVE1") throw new InvalidDataException("Invalid preview protocol");
                    var revision = reader.ReadInt64(); var count = reader.ReadUInt32();
                    // Validate against the remaining record bytes before any
                    // allocation; there is no fixed placement-count ceiling.
                    if (revision <= 0 || count > (input.Length - input.Position) / 56)
                        throw new InvalidDataException("Invalid preview revision or count");
                    var rows = new Placement[count]; var keys = new HashSet<ulong>();
                    for (int i = 0; i < rows.Length; i++)
                    {
                        var p = new Placement { key = reader.ReadUInt64(), uid = reader.ReadUInt32() };
                        var length = reader.ReadUInt32();
                        if (p.key == 0 || p.uid == 0 || !keys.Add(p.key) || length > 4096 || length > input.Length - input.Position)
                            throw new InvalidDataException("Invalid preview placement");
                        p.path = new UTF8Encoding(false, true).GetString(reader.ReadBytes((int)length));
                        if (!p.path.StartsWith("assets/", StringComparison.Ordinal) || !p.path.EndsWith(".prefab", StringComparison.Ordinal)
                            || p.path.Contains("..") || p.path.Contains("\\") || p.path.Contains("\0")) throw new InvalidDataException("Invalid prefab path");
                        p.position = Vector(reader, 3); p.rotation = Vector(reader, 4); p.scale = Vector(reader, 3);
                        double norm = 0; foreach (var value in p.rotation) norm += (double)value * value;
                        if (Math.Abs(norm - 1) > .001) throw new InvalidDataException("Invalid preview rotation");
                        foreach (var value in p.scale) if (Math.Abs(value) < 1e-6) throw new InvalidDataException("Invalid preview scale");
                        rows[i] = p;
                    }
                    if (input.Position != input.Length) throw new InvalidDataException("Unexpected snapshot data");
                    return new Snapshot { revision = revision, placements = rows };
                }
            }
        }
        static float[] Vector(BinaryReader reader, int length)
        {
            var result = new float[length];
            for (int i = 0; i < length; i++)
            {
                result[i] = reader.ReadSingle();
                if (float.IsNaN(result[i]) || float.IsInfinity(result[i]) || Math.Abs(result[i]) >= 1e7)
                    throw new InvalidDataException("Invalid preview transform");
            }
            return result;
        }
    }
    // Pure scheduling primitives shared with offline fixtures. Unity work is
    // supplied by the companion as individual actions, never run on a worker.
    internal sealed class EditStep
    {
        public Action run; public bool mutation;
        public EditStep(Action value,bool changesScene=false){run=value;mutation=changesScene;}
    }
    internal sealed class EditPump : IDisposable
    {
        IEnumerator<EditStep> steps;
        readonly Func<IEnumerator<EditStep>> rollback;
        EditStep pending;
        bool reverting;
        public Exception Error { get; private set; }
        public bool Done { get; private set; }
        public int Completed { get; private set; }
        public EditPump(IEnumerator<EditStep> work,Func<IEnumerator<EditStep>> undo){steps=work;rollback=undo;}
        public void Advance(int maximumMutations=4,int maximumSteps=512,double milliseconds=4)
        {
            var clock=System.Diagnostics.Stopwatch.StartNew();int mutations=0,count=0;
            while(!Done&&count<maximumSteps&&clock.Elapsed.TotalMilliseconds<milliseconds)
            {
                try
                {
                    if(pending==null)
                    {
                        if(!steps.MoveNext()){steps.Dispose();Done=true;break;}
                        pending=steps.Current;
                    }
                    if(pending.mutation&&mutations>=maximumMutations)break;
                    var step=pending;pending=null;count++;if(step.mutation)mutations++;
                    step.run();Completed++;
                }
                catch(Exception error)
                {
                    if(Error==null)Error=error;
                    if(!reverting){steps.Dispose();steps=rollback();reverting=true;pending=null;}
                    // A rejected restore must not prevent cleanup of other
                    // roots. Its original error remains visible to the user.
                }
            }
        }
        public void Dispose(){steps.Dispose();Done=true;pending=null;}
    }
    internal sealed class PlacementDelta
    {
        public readonly Dictionary<ulong,Placement> target=new Dictionary<ulong,Placement>();
        public readonly List<Placement> changed=new List<Placement>();
        public readonly List<ulong> removed=new List<ulong>();
        public PlacementDelta(IDictionary<ulong,Placement> current,Snapshot snapshot,IDictionary<ulong,Placement> immutable)
        {
            foreach(var p in snapshot.placements)target.Add(p.key,p);
            foreach(var entry in immutable)
            {
                Placement p;
                if(!target.TryGetValue(entry.Key,out p)||!entry.Value.SamePlacement(p))
                    throw new InvalidDataException("Compound monument cannot be live-transformed or deleted: "+entry.Value.path+
                        ". Save the new layout and restart preview to rebuild its native map entities.");
            }
            foreach(var p in snapshot.placements){Placement old;if(!current.TryGetValue(p.key,out old)||!old.SamePlacement(p))changed.Add(p);}
            foreach(var key in current.Keys)if(!target.ContainsKey(key))removed.Add(key);
        }
    }
}
