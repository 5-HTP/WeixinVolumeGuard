#define COBJMACROS
#include <windows.h>
#include <mmdeviceapi.h>
#include <endpointvolume.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const GUID enumeratorClass={0xbcde0395,0xe52f,0x467c,{0x8e,0x3d,0xc4,0x57,0x92,0x91,0x69,0x2e}};
static const GUID enumeratorIid={0xa95664d2,0x9614,0x4f35,{0xa7,0x46,0xde,0x8d,0xb6,0x36,0x17,0xe6}};
static const GUID volumeIid={0x5cdf2c82,0x841e,0x4546,{0x97,0x22,0x0c,0xf7,0x40,0x78,0x22,0x9a}};

__attribute__((noinline)) HRESULT target(IAudioEndpointVolume *v,float value) {
    HRESULT result=v->lpVtbl->SetMasterVolumeLevelScalar(v,value,NULL);
    volatile int prevent_tail_call=1;
    return result+prevent_tail_call-1;
}
__attribute__((noinline)) HRESULT other(IAudioEndpointVolume *v,float value) {
    HRESULT result=v->lpVtbl->SetMasterVolumeLevelScalar(v,value,NULL);
    volatile int prevent_tail_call=2;
    return result+prevent_tail_call-2;
}

int main(int argc,char **argv) {
    if(argc!=2) return 2;
    CoInitializeEx(NULL,COINIT_MULTITHREADED);
    IMMDeviceEnumerator *en=NULL; IMMDevice *device=NULL; IAudioEndpointVolume *volume=NULL;
    wchar_t id[1024]; MultiByteToWideChar(CP_UTF8,0,argv[1],-1,id,1024);
    HRESULT hr=CoCreateInstance(&enumeratorClass,NULL,CLSCTX_ALL,&enumeratorIid,(void**)&en);
    if(FAILED(hr)) return 3;
    hr=en->lpVtbl->GetDevice(en,id,&device); if(FAILED(hr)) return 4;
    hr=device->lpVtbl->Activate(device,&volumeIid,CLSCTX_ALL,NULL,(void**)&volume); if(FAILED(hr)) return 5;
    float baseline=0,db=0; BOOL mute=FALSE;
    volume->lpVtbl->GetMasterVolumeLevelScalar(volume,&baseline);
    volume->lpVtbl->GetMute(volume,&mute);
    IAudioEndpointVolume *primary=volume,*secondary=NULL;
    float secondaryBaseline=0; BOOL secondaryMute=FALSE;
    char line[256]; printf("READY %p\n",(void*)volume->lpVtbl->SetMasterVolumeLevelScalar); fflush(stdout);
    while(fgets(line,sizeof(line),stdin)) {
        if(line[0]=='q') break;
        if(line[0]=='s' && secondary==NULL) {
            line[strcspn(line,"\r\n")]=0;
            MultiByteToWideChar(CP_UTF8,0,line+1,-1,id,1024);
            IMMDevice *secondDevice=NULL;
            hr=en->lpVtbl->GetDevice(en,id,&secondDevice);
            if(SUCCEEDED(hr)) {
                hr=secondDevice->lpVtbl->Activate(secondDevice,&volumeIid,CLSCTX_ALL,NULL,(void**)&secondary);
                secondDevice->lpVtbl->Release(secondDevice);
            }
            if(secondary) {
                secondary->lpVtbl->GetMasterVolumeLevelScalar(secondary,&secondaryBaseline);
                secondary->lpVtbl->GetMute(secondary,&secondaryMute);
                volume=secondary;
            }
        }
        if(line[0]=='p') volume=primary;
        float value=(float)atof(line+1);
        if(line[0]=='t') hr=target(volume,value);
        if(line[0]=='n') hr=other(volume,value);
        if(line[0]=='d') hr=volume->lpVtbl->SetMasterVolumeLevel(volume,value,NULL);
        float scalar=0;
        volume->lpVtbl->GetMasterVolumeLevelScalar(volume,&scalar);
        volume->lpVtbl->GetMasterVolumeLevel(volume,&db);
        printf("{\"hr\":%ld,\"scalar\":%.8f,\"db\":%.4f}\n",(long)hr,scalar,db); fflush(stdout);
    }
    primary->lpVtbl->SetMasterVolumeLevelScalar(primary,baseline,NULL);
    primary->lpVtbl->SetMute(primary,mute,NULL);
    if(secondary) {
        secondary->lpVtbl->SetMasterVolumeLevelScalar(secondary,secondaryBaseline,NULL);
        secondary->lpVtbl->SetMute(secondary,secondaryMute,NULL);
        secondary->lpVtbl->Release(secondary);
    }
    primary->lpVtbl->Release(primary); device->lpVtbl->Release(device); en->lpVtbl->Release(en);
    CoUninitialize(); return 0;
}
