param(
    [Parameter(Mandatory=$true)][string]$RustEditPath,
    [Parameter(Mandatory=$true)][string]$Prefab,
    [switch]$RequireChecksum
)
$ErrorActionPreference='Stop'
$managed=Join-Path (Resolve-Path -LiteralPath $RustEditPath).Path 'RustEdit_Data\Managed'
$resolverRoot=$managed
$resolver=[ResolveEventHandler]({param($sender,$eventArgs)
    $name=([Reflection.AssemblyName]::new($eventArgs.Name)).Name
    $path=Join-Path $resolverRoot ($name+'.dll')
    if(Test-Path -LiteralPath $path){return [Reflection.Assembly]::LoadFrom($path)}
    return $null
}.GetNewClosure())
[AppDomain]::CurrentDomain.add_AssemblyResolve($resolver)
try {
    foreach($name in @('LZ4.dll','protobuf-net.dll','Facepunch.System.dll')) {
        [Reflection.Assembly]::LoadFrom((Join-Path $managed $name)) | Out-Null
    }
    $assembly=[Reflection.Assembly]::LoadFrom((Join-Path $managed 'Assembly-CSharp.dll'))
    $type=$assembly.GetType('PrefabSerialization+PrefabData',$true)
    $stream=[IO.File]::OpenRead((Resolve-Path -LiteralPath $Prefab).Path)
    try {
        $header=[byte[]]::new(4)
        if($stream.Read($header,0,4) -ne 4 -or [BitConverter]::ToUInt32($header,0) -ne 1) {throw 'Invalid prefab header'}
        $decoder=[LZ4.LZ4Stream]::new($stream,[LZ4.LZ4StreamMode]::Decompress,[LZ4.LZ4StreamFlags]::None,1048576)
        try {$data=[ProtoBuf.Serializer+NonGeneric]::Deserialize($type,$decoder)} finally {$decoder.Dispose()}
    } finally {$stream.Dispose()}
    $hash=[Checksum]::new()
    foreach($item in $data.prefabs) {
        $hash.Add([uint32]$item.id)
        foreach($vector in @($item.position,$item.rotation,$item.scale)) {
            $hash.Add([single]$vector.x,3);$hash.Add([single]$vector.y,3);$hash.Add([single]$vector.z,3)
        }
    }
    $computed=$hash.MD5()
    if($RequireChecksum -and $computed -ne $data.checksum) {throw 'Current RustEdit checksum does not match'}
    @{placements=$data.prefabs.Count;radius=$data.options.Radius;checksum=$data.checksum;
      calculatedChecksum=$computed;checksumMatches=($computed -eq $data.checksum)} | ConvertTo-Json -Compress
} finally {[AppDomain]::CurrentDomain.remove_AssemblyResolve($resolver)}
