// Offline decoder fixture. No Unity, game or process-inspection dependencies.
using System;
using Ruster.Preview;
class DecoderCheck
{
    static int Main(string[] args)
    {
        if(args.Length!=1)return 2;
        try
        {
            var snapshot=Snapshot.Read(args[0]);
            if(snapshot.placements.Length>0)
            {
                var p=snapshot.placements[0];
                if(p.key!=17||p.uid!=123456||p.position[2]!=-3||p.scale[1]!=2)return 4;
            }
            Console.WriteLine(snapshot.revision+" "+snapshot.placements.Length);return 0;
        }
        catch(Exception error){Console.Error.WriteLine(error.Message);return 1;}
    }
}
