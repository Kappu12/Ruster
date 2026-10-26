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
}
