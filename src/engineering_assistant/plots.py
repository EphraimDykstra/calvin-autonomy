"""Deterministic, grayscale-readable line plots for assignment artifacts.

A plot is described by the physical size it will occupy in the deliverable,
not by a pixel canvas.  ``width`` and ``height`` in a plot spec are **points**
(1/72 inch), the same unit a figure's ``width``/``height`` uses in the solution
schema, so the two declarations can carry the same number.  Text is sized in
points against that target and never falls below ``MIN_TEXT_POINTS``, which is
what makes a small figure a small *readable* figure instead of a shrunken large
one: asking for a narrower plot drops tick marks and tightens padding rather
than shrinking the labels.

The floor holds only if the plot is drawn on the page at the size it was
rendered for, since embedding it at another size rescales the text with it.  So
the plot records its target as its physical size: the PNG's ``pHYs`` chunk holds
the target, and a ``tEXt`` entry under ``PLOT_MARKER_KEY`` says this module
wrote it.  The renderer draws a marked plot at that size when the figure
declares none, and refuses a figure that declares a materially different one.
The key matters because most image tools write ``pHYs`` too, and a foreign one
says nothing about legibility.
"""
from __future__ import annotations
import math
from pathlib import Path
from typing import Any

# The canvas is rendered at this many pixels per point, so the default target
# of 450x292.5pt (6.25in wide) is still drawn on a 1000x650 pixel canvas.
PIXELS_PER_POINT=1000/450
DEFAULT_WIDTH_POINTS=450.0
DEFAULT_HEIGHT_POINTS=292.5
# Text never renders smaller than this on the page, at any target size.
MIN_TEXT_POINTS=7.0
# Axis text is 7.2pt at the default width, matching the previous 16px canvas text.
AXIS_TEXT_FRACTION=1/62.5
TITLE_TEXT_RATIO=22/16
MAX_TARGET_POINTS=1440.0
# Written beside pHYs so the renderer can tell a plot drawn for a size from any
# other PNG that merely carries a resolution.
PLOT_MARKER_KEY='engineering-assistant-plot'
METRES_PER_INCH=0.0254

def _number(value:Any,name:str)->float:
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)

def _target_points(spec:dict)->tuple[float,float]:
    """Physical size the plot is drawn at, in points, defaulting to 6.25in wide."""
    width=spec.get('width'); height=spec.get('height')
    if width is None and height is None: return DEFAULT_WIDTH_POINTS,DEFAULT_HEIGHT_POINTS
    if width is None: width=_number(height,'height')*DEFAULT_WIDTH_POINTS/DEFAULT_HEIGHT_POINTS
    elif height is None: height=_number(width,'width')*DEFAULT_HEIGHT_POINTS/DEFAULT_WIDTH_POINTS
    width=_number(width,'width'); height=_number(height,'height')
    for name,value in (('width',width),('height',height)):
        if value<=0: raise ValueError(f'plot {name} must be a positive number of points')
        if value>MAX_TARGET_POINTS: raise ValueError(f'plot {name} must be at most {MAX_TARGET_POINTS:.0f} points')
    return width,height

def _padded_bounds(low:float,high:float,fraction:float)->tuple[float,float]:
    """Pad an axis range, but never below zero for a non-negative quantity.

    A sum of squared error cannot be negative, so a gridline at -1116 K^2 is a
    drawing artifact that invites the reader to doubt the data.  The padding is
    clamped only when every value is non-negative; genuinely negative data is
    padded as before.
    """
    pad=(high-low)*fraction
    lower=low-pad
    if low>=0 and lower<0: lower=0.0
    return lower,high+pad

def render_line_plot(spec:dict,output:Path)->Path:
    try:
        from PIL import Image,ImageDraw,ImageFont
    except ImportError as exc: raise RuntimeError('Pillow is required to render plots') from exc
    if not isinstance(spec,dict) or not isinstance(spec.get('series'),list) or not spec['series']:
        raise ValueError('plot requires a non-empty series list')
    parsed=[]
    for index,item in enumerate(spec['series']):
        if not isinstance(item,dict) or not isinstance(item.get('x'),list) or not isinstance(item.get('y'),list) or len(item['x'])!=len(item['y']) or len(item['x'])<2:
            raise ValueError(f'series[{index}] requires equal x/y lists with at least two points')
        xs=[_number(v,f'series[{index}].x') for v in item['x']]; ys=[_number(v,f'series[{index}].y') for v in item['y']]
        if item.get('sort_by_x',True):
            pairs=sorted(zip(xs,ys),key=lambda pair:pair[0]); xs=[pair[0] for pair in pairs]; ys=[pair[1] for pair in pairs]
        connect=item.get('connect',True)
        if not isinstance(connect,bool): raise ValueError(f'series[{index}].connect must be true or false')
        parsed.append((str(item.get('name',f'Series {index+1}')),xs,ys,connect))
    all_x=[v for _,xs,_,_ in parsed for v in xs]; all_y=[v for _,_,ys,_ in parsed for v in ys]
    xmin,xmax=min(all_x),max(all_x); ymin,ymax=min(all_y),max(all_y)
    if xmin==xmax or ymin==ymax: raise ValueError('plot axes require nonzero ranges')
    xmin,xmax=_padded_bounds(xmin,xmax,0.06); ymin,ymax=_padded_bounds(ymin,ymax,0.1)

    width_points,height_points=_target_points(spec)
    axis_points=max(MIN_TEXT_POINTS,width_points*AXIS_TEXT_FRACTION)
    # The title takes the same floor rather than a fixed multiple of the axis
    # text, so a dense figure spends its width on the words themselves.
    title_points=max(MIN_TEXT_POINTS,width_points*AXIS_TEXT_FRACTION*TITLE_TEXT_RATIO)
    width=max(1,round(width_points*PIXELS_PER_POINT)); height=max(1,round(height_points*PIXELS_PER_POINT))
    axis_px=max(1,round(axis_points*PIXELS_PER_POINT)); title_px=max(1,round(title_points*PIXELS_PER_POINT))

    def font_at(size:int):
        try: return ImageFont.truetype('DejaVuSans.ttf',size)
        except OSError:
            # Without a scalable face, a bare load_default() ignores the size
            # entirely and every plot renders at one fixed bitmap size, which
            # would silently defeat the legibility rule above.
            try: return ImageFont.load_default(size=size)
            except TypeError: return ImageFont.load_default()

    font=font_at(axis_px); title_font=font_at(title_px)
    image=Image.new('RGB',(width,height),'white'); draw=ImageDraw.Draw(image)
    def text_width(value:str,text_font)->float:
        box=draw.textbbox((0,0),value,font=text_font); return box[2]-box[0]

    def label(value):
        if abs(value)>=100: return f'{value:.0f}'
        if abs(value)>=10: return f'{value:.1f}'
        return f'{value:.2f}'

    def ticks(low,high,count): return [low+(high-low)*i/count for i in range(count+1)]

    title=str(spec.get('title','')); xlabel=str(spec.get('x_label','')); ylabel=str(spec.get('y_label',''))
    def wrap(value:str,text_font,limit:float)->list[str]:
        """Break a caption across lines rather than letting it run off the canvas.

        A narrow figure cannot hold a long title on one line at a legible size,
        and a clipped title fails the requirement that the material, finish and
        computed value be readable *on the graph* just as surely as a tiny one.
        """
        lines=[]; current=''
        for word in value.split():
            candidate=f'{current} {word}'.strip()
            if current and text_width(candidate,text_font)>limit: lines.append(current); current=word
            else: current=candidate
        if current: lines.append(current)
        return lines or ['']
    # Margins follow the text, so they stay readable instead of scaling away.
    gap=axis_px*0.5; tick_len=max(2,round(axis_px*0.375))
    title_lines=wrap(title,title_font,width-2*gap) if title else []
    widest_y=max(text_width(label(v),font) for v in ticks(ymin,ymax,5))
    widest_x=max(text_width(label(v),font) for v in ticks(xmin,xmax,5))
    left=round(widest_y+tick_len+gap)
    right=round(gap+widest_x/2)
    title_height=len(title_lines)*title_px*1.3
    bottom=round(tick_len+gap+axis_px*1.4+(axis_px*1.6 if xlabel else 0))
    # The legend is always placed outside the axes, one row per series.  Inside
    # them it hid any data point under it, and nothing on the page showed that
    # a point was missing (#37).  Three placements are tried in a fixed order and
    # the first that leaves a readable axis is used:
    #   beside  - in the band above the axes, next to the y-axis label; costs no
    #             height for a single series;
    #   stacked - on rows of its own above the axes, for names too wide to sit
    #             beside the label;
    #   column  - to the right of the axes, for a plot too short to give up rows.
    legend_row=axis_px*1.5; legend_rule=axis_px*2.8
    label_row=axis_px*1.5 if ylabel else 0
    rows=len(parsed)*legend_row
    entry_width=max(legend_rule+gap+text_width(name,font) for name,_,_,_ in parsed)
    def placements():
        beside_x=max((left+width-right)/2,gap+(text_width(ylabel,font)+gap*3 if ylabel else 0))
        if beside_x+entry_width<=width-gap:
            yield right,round(title_height+max(label_row,rows)+gap),beside_x,title_height+gap*0.5
        if gap+entry_width<=width-gap:
            yield right,round(title_height+label_row+rows+gap),gap,title_height+label_row+gap*0.5
        top=round(title_height+label_row+gap)
        yield max(right,round(entry_width+gap*3)),top,width-gap-entry_width,top
    for right_margin,top,legend_x,legend_top in placements():
        x0,y0=left,height-bottom; x1,y1=width-right_margin,top
        if x1-x0>=axis_px*4 and y0-y1>=max(axis_px*4,legend_top+rows-top): break
    else:
        raise ValueError('plot target size is too small to draw a readable axis beside its title, labels and legend')

    # Tick density is a function of the space a label actually needs, so a small
    # plot drops ticks rather than overprinting them.
    x_steps=max(1,min(5,int((x1-x0)/max(1.0,widest_x*1.5))))
    y_steps=max(1,min(5,int((y0-y1)/max(1.0,axis_px*3))))
    axis_width=max(1,round(axis_px*0.125))
    draw.line((x0,y0,x1,y0),fill='black',width=axis_width); draw.line((x0,y0,x0,y1),fill='black',width=axis_width)
    def px(x): return x0+(x-xmin)/(xmax-xmin)*(x1-x0)
    def py(y): return y0-(y-ymin)/(ymax-ymin)*(y0-y1)
    for xv in ticks(xmin,xmax,x_steps):
        xx=px(xv); text=label(xv)
        draw.line((xx,y0,xx,y0+tick_len),fill='black',width=axis_width)
        draw.text((xx-text_width(text,font)/2,y0+tick_len+gap*0.5),text,fill='black',font=font)
    for yv in ticks(ymin,ymax,y_steps):
        yy=py(yv); text=label(yv)
        draw.line((x0-tick_len,yy,x0,yy),fill='black',width=axis_width)
        draw.text((x0-tick_len-gap*0.5-text_width(text,font),yy-axis_px*0.6),text,fill='black',font=font)

    patterns=[None,12,5]
    shades=['black','#555555','#999999']
    line_width=max(1,round(axis_px*0.19)); marker=max(1,round(axis_px*0.31))
    for index,(name,xs,ys,connect) in enumerate(parsed):
        points=[(px(x),py(y)) for x,y in zip(xs,ys)]; dash=patterns[index%len(patterns)]; color=shades[index%len(shades)]
        for a,b in zip(points,points[1:]) if connect else []:
            if dash is None: draw.line((a,b),fill=color,width=line_width)
            else:
                dx,dy=b[0]-a[0],b[1]-a[1]; length=math.hypot(dx,dy); steps=max(1,int(length/dash))
                for j in range(0,steps,2):
                    s=j/steps; e=min((j+1)/steps,1); draw.line((a[0]+dx*s,a[1]+dy*s,a[0]+dx*e,a[1]+dy*e),fill=color,width=line_width)
        for x,y in points:
            draw.ellipse((x-marker,y-marker,x+marker,y+marker),outline=color,fill='white',width=max(1,round(axis_px*0.125)))
    for index,(name,_,_,_) in enumerate(parsed):
        color=shades[index%len(shades)]
        ly=legend_top+legend_row*(index+0.5)
        draw.line((legend_x,ly,legend_x+legend_rule,ly),fill=color,width=line_width)
        draw.text((legend_x+legend_rule+gap,ly-axis_px*0.6),name,fill='black',font=font)
    for line_index,line in enumerate(title_lines):
        draw.text(((width-text_width(line,title_font))/2,gap*0.5+line_index*title_px*1.3),line,fill='black',font=title_font)
    if xlabel:
        draw.text(((width-text_width(xlabel,font))/2,height-axis_px*1.5),xlabel,fill='black',font=font)
    if ylabel: draw.text((gap,title_height+gap*0.5),ylabel,fill='black',font=font)
    # pHYs stores whole pixels per metre, per axis.  Each axis gets the density
    # that makes its own pixel count come out at the target, so the rounding of
    # the canvas to whole pixels does not leak into the physical size.
    from PIL.PngImagePlugin import PngInfo
    provenance=PngInfo(); provenance.add_text(PLOT_MARKER_KEY,'pHYs is the target size')
    def density(pixels:int,points:float)->float:
        return round(pixels/(points/72)/METRES_PER_INCH)*METRES_PER_INCH
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    image.save(output,'PNG',pnginfo=provenance,dpi=(density(width,width_points),density(height,height_points)))
    return output
