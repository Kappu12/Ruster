// Offline decoder fixture. No Unity, game or process-inspection dependencies.
using System;
using System.IO;
using System.Collections.Generic;
using Ruster.Preview;
class DecoderCheck
{
    static IEnumerable<EditStep> Work(Action run,int count,bool fail=false)
    {
        for(int i=0;i<count;i++)yield return new EditStep(run,true);
        if(fail)yield return new EditStep(()=>{throw new InvalidOperationException("late failure");});
    }
    static void QueueCheck()
    {
        int applied=0,undone=0,slices=0;
        using(var pump=new EditPump(Work(()=>applied++,1200).GetEnumerator(),()=>Work(()=>undone++,applied).GetEnumerator()))
        {
            while(!pump.Done)
            {
                int before=applied;pump.Advance(3);slices++;
                if(applied-before>3||slices>10000)throw new Exception("Server queue exceeded its slice bound");
            }
            if(applied!=1200||slices<400||undone!=0)throw new Exception("Server update did not yield");
        }
        applied=undone=0;
        using(var pump=new EditPump(Work(()=>applied++,31,true).GetEnumerator(),()=>Work(()=>undone++,applied).GetEnumerator()))
        {
            while(!pump.Done){int before=undone;pump.Advance(2);if(undone-before>2)throw new Exception("Rollback exceeded its budget");}
            if(pump.Error==null||undone!=31)throw new Exception("A late failure was not rolled back incrementally");
        }
        var current=new Dictionary<ulong,Placement>();var rows=new Placement[10000];
        for(int i=0;i<rows.Length;i++){rows[i]=new Placement{key=(ulong)i+1,uid=1,path="assets/test.prefab",position=new float[3],rotation=new float[]{0,0,0,1},scale=new float[]{1,1,1}};current.Add(rows[i].key,rows[i]);}
        var immutable=new Dictionary<ulong,Placement>{{1,rows[0]}};
        rows[5000]=new Placement{key=5001,uid=1,path="assets/test.prefab",position=new float[]{1,0,0},rotation=new float[]{0,0,0,1},scale=new float[]{1,1,1}};
        var delta=new PlacementDelta(current,new Snapshot{revision=2,placements=rows},immutable);
        if(delta.changed.Count!=1||delta.changed[0].key!=5001||delta.removed.Count!=0)throw new Exception("Unchanged server placements were not skipped");
        try{new PlacementDelta(current,new Snapshot{revision=3,placements=new Placement[0]},immutable);throw new Exception("Immutable monument deletion accepted");}catch(InvalidDataException){}
    }
    static int Main(string[] args)
    {
        if(args.Length==1&&args[0]=="--queue"){QueueCheck();return 0;}
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
