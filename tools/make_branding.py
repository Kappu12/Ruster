#!/usr/bin/env python3
"""Build crisp app graphics from a vector mark and a locally supplied Rust font.

The font is a build input only; its font software is never shipped with Ruster.
"""
import argparse
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
# Rust's radial exclamation mark, without the square behind it. Shared geometry
# produces identical small/large icons; no thresholded or distressed bitmap edges.
SHAPES=[[(167,46),(252,46),(238,131),(181,131)],
        [(181,145),(238,145),(238,174),(181,174)],
        [(47,166),(89,177),(132,180),(132,238),(89,242),(47,252)],
        [(146,180),(174,180),(174,238),(146,238)],
        [(209,189),(230,210),(209,231),(188,210)],
        [(254,214),(275,235),(235,275),(214,254)],
        [(285,244),(311,265),(355,294),(294,355),(269,316),(244,285)]]


def mark(size,color):
    factor=4
    image=Image.new('RGBA',(size*factor,size*factor))
    draw=ImageDraw.Draw(image)
    scale=size*factor/400
    for polygon in SHAPES:draw.polygon([(x*scale,y*scale) for x,y in polygon],fill=color)
    return image.resize((size,size),Image.Resampling.LANCZOS)


def lettering(font_path,width,color):
    font=ImageFont.truetype(str(font_path),300)
    box=font.getbbox('RUSTER')
    image=Image.new('RGBA',(box[2]-box[0]+4,box[3]-box[1]+4))
    ImageDraw.Draw(image).text((2-box[0],2-box[1]),'RUSTER',font=font,fill=color)
    height=round(image.height*width/image.width)
    return image.resize((width,height),Image.Resampling.LANCZOS)


def build(font_path,output):
    output.mkdir(parents=True,exist_ok=True)
    white=(235,235,232,255);black=(28,30,29,255)
    for name,color in [('white',white),('black',black)]:
        icon=mark(512,color);icon.save(output/f'icon-{name}.png')
        polygons=''.join('<polygon points="'+' '.join(f'{x},{y}' for x,y in points)+'"/>' for points in SHAPES)
        (output/f'icon-{name}.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><g fill="'+('#ebebe8' if name=='white' else '#1c1e1d')+'">'+polygons+'</g></svg>')
        # Native Blender popup image previews are square. A stacked lockup
        # keeps the actual Rust-font name readable within that supported UI.
        welcome=Image.new('RGBA',(512,512))
        welcome.alpha_composite(mark(350,color),(81,0))
        name_image=lettering(font_path,460,color)
        welcome.alpha_composite(name_image,(26,377-name_image.height//2))
        welcome.save(output/f'welcome-{name}.png')
    icon=mark(512,white)
    icon.save(output/'ruster.ico',sizes=[(s,s) for s in (16,20,24,32,40,48,64,128,256)])
    word=lettering(font_path,1320,white)
    logo=Image.new('RGBA',(1800,360))
    logo.alpha_composite(mark(350,white),(10,5))
    logo.alpha_composite(word,(405,(360-word.height)//2))
    logo.save(output/'wordmark.png')
    splash=Image.new('RGBA',(1000,500),(26,27,27,255))
    draw=ImageDraw.Draw(splash)
    # Quiet drafting grid ties the branding to prefab composition.
    for x in range(-1000,2000,80):draw.line((x,500,x+500,0),fill=(32,34,33,255),width=1)
    for y in range(0,501,50):draw.line((0,y,1000,y),fill=(32,34,33,255),width=1)
    splash.alpha_composite(mark(270,white),(55,100))
    title=lettering(font_path,580,white)
    splash.alpha_composite(title,(344,215-title.height//2))
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',22)
    draw.text((348,302),'R U S T   P R E F A B   S T U D I O',font=font,fill=(148,154,149,255))
    splash.convert('RGB').save(output/'splash.png')
    print('BRANDING_READY',output)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--font',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'ruster/branding')
    args=parser.parse_args();build(args.font,args.output)
