// Offline decoder fixture. No Unity, game or process-inspection dependencies.
using System;
using System.IO;
using Ruster.Preview;
class DecoderCheck
{
    static int Main(string[] args)
    {
        if(args.Length==2&&args[0]=="--peer")
        {
            foreach(var port in new uint[]{0,65536})
            {
                try{PeerProof.Encode(new string('a',64),123,port,10000,"http://127.0.0.1:12345/test.map");return 5;}
                catch(InvalidDataException){}
            }
            try{PeerProof.Encode(new string('a',64),123,23456,10000,"http://example.com/test.map");return 5;}
            catch(InvalidDataException){}
            try{PeerProof.Encode(new string('x',64),123,23456,10000,"http://127.0.0.1:12345/test.map");return 5;}
            catch(FormatException){}
            File.WriteAllBytes(args[1],PeerProof.Encode(new string('a',64),123,23456,10000,"http://127.0.0.1:12345/test.map"));
            return 0;
        }
        if(args.Length!=1)return 2;
        try
        {
            var snapshot=Snapshot.Read(args[0]);
            if(snapshot.placements.Length>0)
            {
                var p=snapshot.placements[0];
                if(p.key!=17||p.uid!=123456||p.position[2]!=-3||p.scale[1]!=2)return 4;
                var same=new Placement{key=p.key,uid=p.uid,path=p.path,position=(float[])p.position.Clone(),
                    rotation=(float[])p.rotation.Clone(),scale=(float[])p.scale.Clone()};
                if(!p.SamePlacement(same)||p.SamePlacement(null))return 6;
                same.position[0]+=1;if(p.SamePlacement(same))return 6;same.position[0]=p.position[0];
                same.rotation[0]+=.1f;if(p.SamePlacement(same))return 6;same.rotation[0]=p.rotation[0];
                same.scale[0]*=2;if(p.SamePlacement(same))return 6;same.scale[0]=p.scale[0];
                same.uid++;if(p.SamePlacement(same))return 6;
            }
            Console.WriteLine(snapshot.revision+" "+snapshot.placements.Length);return 0;
        }
        catch(Exception error){Console.Error.WriteLine(error.Message);return 1;}
    }
}
