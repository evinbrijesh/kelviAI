(()=>{var Qa={none:3,flow:1,orb:2,drift:4,swell:5,caustics:6,contour:7,aurora:8,ripple:9,halo:10,interference:11,mesh:12,cascade:13,constellation:14},ua=e=>e?`
const float VSCALE=6.;
vec4 decodeFluid(vec4 t){return vec4((t.xy*2.-1.)*VSCALE,t.z,t.w);}
vec4 encodeFluid(vec4 v){return vec4(clamp(v.xy/VSCALE*.5+.5,0.,1.),clamp(v.z,0.,1.),1.);}`:`
vec4 decodeFluid(vec4 t){return t;}
vec4 encodeFluid(vec4 v){return vec4(v.xyz,1.);}`,ha=e=>`#version 300 es
precision highp float;
precision highp sampler2D;
uniform sampler2D uSource, uFluid;
uniform vec2 uResolution, uCell;
uniform float uCount, uBlend;
const float BAYER[16]=float[16](0.,8.,2.,10.,12.,4.,14.,6.,3.,11.,1.,9.,15.,7.,13.,5.);
uniform vec3 uRamp[6];
uniform float uRampCount;
// The gradient map: the tone run through the ramp's stops, evenly spaced, faintest first.
vec3 rampAt(float t){
  float x=clamp(t,0.,1.)*(uRampCount-1.);
  int i=int(min(floor(x),uRampCount-2.));
  vec3 a=uRamp[0],b=uRamp[1];
  for(int k=1;k<5;k++)if(k==i){a=uRamp[k];b=uRamp[k+1];}
  return mix(a,b,clamp(x-float(i),0.,1.));
}
uniform vec4 uSourceMap;
uniform int uScene;
uniform vec3 uInk, uHighlight;
uniform vec4 uBackground;
uniform float uBrightness, uContrast, uGamma, uInvert, uVignette, uSourceColor;
uniform float uRefraction, uGlow, uTime, uDrift, uFluidOn, uLod, uSaturation, uBackdrop, uShade, uHighlightAuto, uFluidMode;
uniform vec2 uFluidTexel;
uniform int uHoverMode;
uniform vec3 uLight;
uniform vec3 uTrail[12];
uniform float uLightRadius, uLightGain, uClock, uFlicker, uTrailAmount;
uniform sampler2D uTrailMap, uScope;
uniform float uScopeMode;
uniform vec2 uLevels;
uniform int uMark;
uniform float uScale, uClearFeather, uClearShape, uOrder;
// Text order by rows: each word's first glyph index and length, and how many words there are (0 reads the charset as one stream).
uniform vec2 uWords[8];
uniform float uWordCount;
uniform vec4 uClear;
uniform vec4 uPulse[4];
uniform sampler2D uTapMap;
uniform float uTapOn;
uniform sampler2D uClearMap;
uniform float uClearMapOn, uClearBend;
uniform vec2 uClearTexel;
layout(location=0) out vec4 outInk;
layout(location=1) out vec4 outUnder;
${ua(e)}
float hash(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p),u=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),u.x),u.y);}
float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*noise(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return v;}
vec3 generated(vec2 uv,float aspect){
  vec2 p=(uv-.5)*vec2(aspect,1.)*uScale;
  if(uScene==1){
    float t=uTime*.08;
    vec2 q=vec2(fbm(p*1.6+t),fbm(p*1.6-t+3.1));
    return vec3(smoothstep(.28,.86,fbm(p*1.8+q*1.6+vec2(t*.6,-t*.4))));
  }
  if(uScene==2){
    float r=.36,d=length(p),a=uTime*.25;
    vec3 l=normalize(vec3(cos(a)*.8,.55,sin(a)*.6+.6));
    if(d<r){
      vec3 n=normalize(vec3(p.x,-p.y,sqrt(r*r-d*d)));
      float diffuse=max(dot(n,l),0.),rim=pow(1.-n.z,2.5);
      float lon=atan(n.x,n.z)+uTime*.35,lat=asin(clamp(n.y,-1.,1.));
      float bands=.5+.25*sin(lat*14.)+.25*sin(lon*6.);
      return vec3(clamp(diffuse*.85+rim*.5+bands*.12,0.,1.));
    }
    return vec3(exp(-pow((d-r)*9.,2.))*.35);
  }
  if(uScene==4){
    // Drift: a few broad lobes that wander slowly. Built for halftone, where large soft shapes read best.
    float t=uTime*.045;
    vec2 q=p*1.15;
    vec2 w=vec2(fbm(q*.7+vec2(t,-t*.7)),fbm(q*.7+vec2(4.3-t*.8,t+1.7)));
    float n=fbm(q+w*1.3+vec2(t*.4,t*.25));
    return vec3(smoothstep(.36,.74,n));
  }
  if(uScene==5){
    // Swell: three crossing swells, the second bent by the first, so crests roll diagonally instead of pooling.
    float t=uTime;
    float s=sin((dot(p,vec2(.94,.33))/.95-t/9.)*6.2831853);
    float c=sin((dot(p,vec2(.6,-.8))/.58-t/13.)*6.2831853+s*.9);
    float k=sin((dot(p,vec2(-.29,.96))/.36+t/17.)*6.2831853);
    return vec3(smoothstep(.3,.9,.5+.5*(s*.5+c*.35+k*.15)));
  }
  // The kit's background scenes. Each starts a little way in, so a reduced-motion still is already composed.
  float t=uTime+40.,px=uCell.y/uResolution.y*uScale;
  if(uScene==6){
    // Caustics: light focused by a moving water surface. Two layers of warped sine waves drift against each other; each draws
    // smooth filaments along its zero line, about a character wide. Where they cross the light lifts a little, never to a blot.
    float tt=t*.12,a=0.,b=0.;
    for(int l=0;l<2;l++){
      float f=float(l),sc=5.4+f*2.4;
      vec2 q=(l==0?p:mat2(.8,-.6,.6,.8)*p)*sc;
      q+=vec2(sin(q.y*.45+tt*(1.+f*.3)),cos(q.x*.4-tt*(.8+f*.4)))*1.3;
      float v=sin(q.x+1.4*sin(q.y*.7+tt))+sin(q.y*1.1+1.2*sin(q.x*.8-tt*1.3))*.9;
      float wv=max(fwidth(v),1e-4);
      float line=(1.-smoothstep(.2,1.5,abs(v)/wv))*(l==0?.78:.62)+exp(-abs(v)/(wv*5.))*.16;
      if(l==0)a=line;else b=line;
    }
    float pulse=.85+.15*sin(tt*3.+p.x*1.7-p.y*1.1);
    float light=max(a,b)+.3*min(a,b);
    return vec3(clamp(light*light*pulse,0.,.78));
  }
  if(uScene==7){
    // Contour: a slow terrain read as survey lines about a character wide at any size; every fifth is an index line.
    float tt=t*.02;
    vec2 q=p*1.15+vec2(tt,-tt*.6);
    float h=noise(q)*.62+noise(q*2.07+3.1)*.27+noise(q*4.3-tt+7.)*.11;
    h+=.08*sin(tt*2.+p.x*.8);
    float k=h*13.,w=max(fwidth(k),1e-4),d=abs(fract(k+.5)-.5)/w;
    float major=mod(floor(k+.5),5.)<.5?1.:0.;
    return vec3((1.-smoothstep(.35,1.25-major*.25,d))*mix(.55,1.,major));
  }
  if(uScene==8){
    // Aurora: three curtains at different distances hang from the top. Far ones sit higher and dimmer; the nearest is tallest
    // and brightest. Each folds slowly and is brightest along its lower hem, fading upward. The rays are set per character
    // column, so the curtains read as vertical strokes at any stage size, from a small card to a phone.
    float tt=t*.05,a=0.,cw=uCell.x/uResolution.x;
    float col=floor(uv.x/cw+.5);
    for(int n=0;n<3;n++){
      float f=float(n),near=f/2.;
      float x=p.x*(1.3-near*.4)+f*3.7;
      float hem=-.28+near*.3+.16*sin(x*1.3+tt*(.9+f*.25)+f*2.)+.045*sin(x*3.4-tt*1.5+f);
      float d=hem-p.y;
      float body=d>0.?exp(-d/(.14+near*.26))*(.45+.55*exp(-d/.03)):exp(-d*d/.0002);
      float fold=.5+.5*sin(x*2.1+tt*.9+f*1.7+.7*sin(x*.8-tt*.6));
      float ray=mix(hash(vec2(col,f*7.1)),noise(vec2(col*.18+f*9.,tt*.7+f)),.55);
      float layer=clamp(body*(.1+.9*fold*fold)*(.2+.8*ray)*(.4+near*.6)*4.2,0.,1.);
      a=1.-(1.-a)*(1.-layer);
    }
    return vec3(smoothstep(.12,.9,a));
  }
  if(uScene==9){
    // Ripple: still water. Drops land here and there, each a few rings that widen and fade; the pointer drops its own.
    float tone=0.,g=.72;
    vec2 q=p/g,id=floor(q);
    for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){
      vec2 c=id+vec2(i,j),h=vec2(hash(c),hash(c+7.3));
      float period=5.+h.x*5.,age=fract(t*.3/period*4.+h.y);
      vec2 at=(c+.2+.6*h)*g;
      float d=length(p-at),r=age*.62;
      float rings=max(0.,cos((d-r)*34.))*exp(-pow((d-r)/.11,2.));
      tone+=rings*pow(1.-age,1.8)*smoothstep(0.,.06,age)*(.7+.3*h.x);
    }
    return vec3(clamp(tone*1.25,0.,1.));
  }
  if(uScene==10){
    // Halo: a slow breathing corona that frames the content, its rays turning. The ring fits the stage: wide on a desktop
    // hero, tall on a phone, so the whole halo stays on screen; the middle stays empty for a headline.
    vec2 r=vec2(min(.46,aspect*.4),min(.34,.36/max(aspect,.01)*.5+.2));
    vec2 e=p/r;
    float d=length(e),a=atan(e.y,e.x),tt=t*.07,k=min(r.x,r.y);
    float breathe=1.+.04*sin(tt*3.1);
    float rays=.5+.5*noise(vec2(a*3.2+tt,tt*.5))*(.6+.4*noise(vec2(a*7.-tt*1.2,3.+tt*.4)));
    float s=(d-breathe)*k;
    float rim=exp(-pow(s/.03,2.));
    float corona=exp(-max(0.,s)/(.1+.08*rays))*smoothstep(-.04,.015,s)*rays*smoothstep(.36,.12,s);
    return vec3(clamp(rim*(.55+.45*rays)+corona*.85,0.,1.));
  }
  if(uScene==11){
    // Interference: two ring grids from slowly orbiting centres. Where they cross, broad moire bands open and close.
    float tt=t*.05;
    vec2 a=vec2(-.3+.12*sin(tt),.07*cos(tt*1.3)),b=vec2(.3+.1*cos(tt*.8),-.06*sin(tt*1.1));
    float f=6.2831853/max(px*4.6,.004);
    float m=cos(length(p-a)*f)+cos(length(p-b)*f);
    return vec3(smoothstep(.7,2.,m));
  }
  if(uScene==12){
    // Mesh: four soft lights on slow Lissajous paths, a gradient mesh written in characters.
    float tt=t*.07,m=0.;
    for(int n=0;n<4;n++){
      float f=float(n)*1.7;
      vec2 c=vec2(.66*sin(tt*(.7+f*.13)+f),.34*cos(tt*(.9-f*.07)+f*1.3));
      float s=.3+.07*sin(tt+f);
      m+=exp(-dot(p-c,p-c)/(s*s))*(.8-float(n)*.1);
    }
    return vec3(smoothstep(.06,1.1,m));
  }
  if(uScene==13){
    // Cascade: streaks fall in three depths. Far ones are frequent, faint, short and slow; near ones rare, long, bright and
    // quick. Each has a bright head and a tail that fades behind it, and a column can carry two streaks at once.
    float tone=0.,cw=uCell.x/uResolution.x,ch=uCell.y/uResolution.y;
    float col=floor(uv.x/cw+.5);
    for(int n=0;n<3;n++){
      float f=float(n);
      for(int k=0;k<2;k++){
        float seed=f*13.1+float(k)*41.7,h=hash(vec2(col,seed));
        if(h<1.-(.5-f*.15))continue;
        float speed=(.045+f*.07)*(.75+.5*hash(vec2(col,seed+2.)));
        float tail=.12+f*.16,y=fract(t*speed+hash(vec2(col,seed+5.)))*(1.+tail*2.)-tail;
        float d=y-uv.y;
        if(d<0.||d>tail)continue;
        float head=d<ch*1.2?1.:0.;
        tone=max(tone,max(head*(.55+f*.22),pow(1.-d/tail,1.7)*(.28+f*.3)));
      }
    }
    return vec3(clamp(tone,0.,1.));
  }
  if(uScene==14){
    // Constellation: points wander in their own cells; neighbours close enough are linked by fine lines. Each point is a
    // bright core in a soft halo, so it reads at card size as well as full width.
    float g=.23,tt=t*.18;
    vec2 q=p/g,id=floor(q);
    vec2 pts[9];
    for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){
      vec2 c=id+vec2(i,j);
      float h=hash(c),k=hash(c+3.7);
      pts[(j+1)*3+i+1]=c+.5+.36*vec2(sin(tt*(.6+h)+h*6.28),cos(tt*(.5+k)+k*6.28));
    }
    float line=0.,star=0.,lw=max(px/g,.02);
    for(int n=0;n<9;n++){
      vec2 e=q-pts[n];
      float d2=dot(e,e),tw=.8+.2*sin(tt*3.+float(n)*1.7);
      star=max(star,max(exp(-d2/(lw*lw*1.6)),.38*exp(-d2/(lw*lw*7.)))*tw);
      for(int m=n+1;m<9;m++){
        vec2 a=pts[n],ba=pts[m]-a;
        float len=length(ba);
        if(len>1.35)continue;
        float hh=clamp(dot(q-a,ba)/dot(ba,ba),0.,1.);
        float d=length(q-a-ba*hh);
        line=max(line,(1.-smoothstep(lw*.3,lw*.75,d))*smoothstep(1.35,.6,len)*.72);
      }
    }
    return vec3(clamp(max(line,star),0.,1.));
  }
  return vec3(0.);
}
// Hover scope: 1 where the pointer response may act. The map holds the source's soft subject coverage in alpha.
float hoverScope(vec2 uv){
  if(uScopeMode<.5||uScene!=0)return 1.;
  vec2 s=uv*uSourceMap.xy+uSourceMap.zw;
  float c=(s.x<0.||s.y<0.||s.x>1.||s.y>1.)?0.:texture(uScope,s).a;
  return uScopeMode<1.5?c:1.-c;
}
void main(){
  vec2 cell=floor(gl_FragCoord.xy);
  vec2 uv=(cell+.5)*uCell/uResolution;
  float aspect=uResolution.x/uResolution.y;
  float hs=hoverScope(uv);
  vec4 fluid=vec4(0.);
  // lift: signed tone change. The solver's flow brightens one side of each eddy and opens the other into gaps.
  float lift=0.,wake=0.,bend=1.,swirl=0.,speed=0.;
  if(uFluidOn>.5){
    vec4 raw=texture(uFluid,vec2(uv.x,1.-uv.y));
    if(uFluidMode>.5){
      vec2 v=raw.xy*uFluidTexel*vec2(aspect,1.)*hs;
      fluid=vec4(v,0.,1.);
      swirl=clamp(dot(v,vec2(.4,.65))*uGlow*.32,-.65,.65);
      speed=clamp(length(v)*uGlow*.055,0.,.38);
      bend=.4;
    } else {
      fluid=decodeFluid(raw);
      fluid.xyz*=hs;
      wake=clamp(fluid.z*uGlow,0.,1.);
      lift=wake*.55;
    }
  }
  vec2 drift=uDrift*.006*vec2(sin(uv.y*5.3+uTime*.6),cos(uv.x*4.1-uTime*.5));
  vec2 sampleAt=uv-vec2(fluid.x/aspect,-fluid.y)*uRefraction*bend+drift;
  float keep=0.;
  if(uClearMapOn>0.){
    // Text-shaped clear map: quiet right behind the content, and the field leans away from its edges so it flows round them.
    keep=texture(uClearMap,uv).r;
    vec2 t=uClearTexel*1.5;
    vec2 g=vec2(texture(uClearMap,uv+vec2(t.x,0.)).r-texture(uClearMap,uv-vec2(t.x,0.)).r,texture(uClearMap,uv+vec2(0.,t.y)).r-texture(uClearMap,uv-vec2(0.,t.y)).r);
    sampleAt+=g*vec2(1./aspect,1.)*uClearBend;
  }
  float spot=0.;
  if(uHoverMode==4||uHoverMode==5){
    vec2 d=(uv-uLight.xy)*vec2(aspect,1.);
    float q2=dot(d,d)/(uLightRadius*uLightRadius*2.2);
    // Loupe: flat-topped zoom with a soft rim. Reveal: a soft spot in the source's colours.
    if(uHoverMode==4) sampleAt-=(uv-uLight.xy)*exp(-q2*q2)*.45*uLight.z*min(1.,uLightGain*1.6)*hs;
    else spot=exp(-q2*1.6)*uLight.z*min(1.,uLightGain*1.6)*hs;
  }
  vec3 rgb,glow=vec3(0.);
  if(uScene==0){
    vec2 s=sampleAt*uSourceMap.xy+uSourceMap.zw;
    bool inside=!(s.x<0.||s.y<0.||s.x>1.||s.y>1.);
    rgb=inside?textureLod(uSource,s,uLod).rgb:vec3(0.);
    if(uBackdrop>0.){
      vec2 b=(uv-vec2(fluid.x/aspect,-fluid.y)*uRefraction*bend*.5)*uSourceMap.xy+uSourceMap.zw;
      glow=(b.x<0.||b.y<0.||b.x>1.||b.y>1.)?vec3(0.):textureLod(uSource,b,uLod+3.).rgb*uBackdrop;
    }
  } else rgb=generated(sampleAt,aspect);
  float tone=dot(rgb,vec3(.2126,.7152,.0722));
  tone=clamp((tone-uLevels.x)/max(uLevels.y-uLevels.x,.01),0.,1.);
  tone=clamp((tone-.5)*uContrast+.5+uBrightness,0.,1.);
  tone=pow(tone,1./uGamma);
  if(uInvert>.5)tone=1.-tone;
  float flick=0.,trailFold=0.;
  // Reveal: under the spot the characters take the source's own colour and a little more ink.
  if(spot>0.)lift=spot*.22;
  if(uHoverMode==2){
    // Lantern: a soft light and its fading tail lift the characters they pass. Nothing moves the image.
    vec2 ap=vec2(aspect,1.),d=(uv-uLight.xy)*ap;
    float r2=uLightRadius*uLightRadius,glowL=uLight.z*exp(-dot(d,d)/r2);
    for(int i=0;i<12;i++){vec2 e=(uv-uTrail[i].xy)*ap;glowL+=uTrail[i].z*exp(-dot(e,e)/(r2*.55));}
    glowL=min(glowL,1.)*hs;
    float grain=fract(sin(dot(cell,vec2(12.9898,78.233)))*43758.5453);
    lift=glowL*uLightGain*(.7+.6*grain);
    wake=glowL*.4;
    // A few letters at the light's rim step up the ramp and back, as if being retyped.
    flick=uFlicker*step(.9,fract(grain*13.7+floor(uClock*7.+grain*5.)*.37))*glowL*(1.-glowL)*4.;
  }
  if(uHoverMode==3){
    // Trail: the studio's ink field, as a 16-bit density. Sparse marks fill in, dense marks open up.
    vec4 ink=texture(uTrailMap,uv);
    float density=(ink.r*65280.+ink.g*255.)/65535.*uTrailAmount;
    float t=clamp(density/.38,0.,1.);
    trailFold=t*t*(3.-2.*t)*hs;
  }
  if(uFluidMode>.5&&uHoverMode==1){
    // Dark ground: any motion lights the characters. Lit ground: the flow lights one side of each eddy and opens the other.
    // A little cell-to-cell grain keeps the lit area a shimmer of letters rather than a solid block.
    float grain=fract(sin(dot(cell,vec2(12.9898,78.233)))*43758.5453);
    lift=mix(abs(swirl)*.5+speed,swirl+speed*.35,smoothstep(.12,.55,tone))*(.65+.7*grain);
    wake=clamp(lift*1.6,0.,1.);
  }
  tone=clamp(tone+lift,0.,1.);
  tone+=(1.-2.*tone)*trailFold;
  // Pulses: rings sent by the interface (field.pulse()), e.g. on a save or a notification.
  for(int i=0;i<4;i++){
    if(uPulse[i].w<=0.)continue;
    float dist=length((uv-uPulse[i].xy)*vec2(aspect,1.)),front=uPulse[i].z*.95;
    float ring=exp(-pow((dist-front)/.1,2.))*uPulse[i].w*exp(-uPulse[i].z*.85);
    tone=clamp(tone+ring*.85,0.,1.);
  }
  if(uTapOn>0.){
    // A surface tap: a signed lift (16 bits) and a glint, worked out on the CPU over the photo's own medium.
    vec4 tap=texture(uTapMap,uv);
    float lift=(tap.r*65280.+tap.g*255.)/65535.*2.-1.;
    tone=clamp(tone+(lift*1.25+tap.b)*uTapOn,0.,1.);
  }
  tone*=1.-uVignette*smoothstep(.35,1.05,length((uv-.5)*vec2(min(aspect,1.8),1.)*2.));
  if(uClearMapOn>0.)tone*=1.-uClearMapOn*smoothstep(0.,1.,keep);
  if(uClear.z>0.){
    // Clear zone: the field fades out around content so text above it stays readable.
    vec2 half_=uClear.zw*.5*vec2(aspect,1.),q=(uv-uClear.xy-uClear.zw*.5)*vec2(aspect,1.);
    float dz;
    if(uClearShape>.5){vec2 e=abs(q)-half_;dz=length(max(e,0.))+min(max(e.x,e.y),0.);}
    else dz=(length(q/max(half_,vec2(1e-4)))-1.)*min(half_.x,half_.y);
    tone*=smoothstep(0.,uClearFeather,dz);
  }
  // Blend: a shade between two characters takes the upper one in the share of cells a 4x4 Bayer pattern gives it.
  float level=tone*(uCount-1.),upper=fract(level)>=.5?1.:0.;
  if(uBlend>.5&&tone>.02&&tone<.98){
    ivec2 q=ivec2(mod(gl_FragCoord.xy,4.));
    upper=fract(level)>(BAYER[q.y*4+q.x]+.5)/16.?1.:0.;
  }
  float index=min(uCount-1.,floor(level)+upper+(flick>.5&&tone>.02?1.:0.));
  if(uOrder>1.5){
    // Scatter order: each cell keeps one character picked from the charset by a hash of its place, and the tone sets how
    // strongly it shows rather than which character it is, so a field of letters brightens and fades like a lit screen.
    index=tone>.008?1.+min(uCount-2.,floor(hash(cell*.731+vec2(19.17,3.71))*(uCount-1.))):0.;
  } else if(uOrder>.5){
    // Text order: the charset after its blank is read in sequence along each row, each row a few letters on, so words stay
    // legible. Every letter is there; the tone sets how strongly it shows, so the words fade out toward the field's quiet edges.
    float n=max(1.,uCount-1.);
    index=tone>.015?1.+mod(cell.x+cell.y*(floor(n*.38)+1.),n):0.;
    if(uWordCount>.5&&tone>.015){
      // One word a row, repeated with a space between, rows taking the words in turn and each a few letters along.
      int k=int(mod(cell.y,uWordCount));
      vec2 word=uWords[0];
      for(int i=1;i<8;i++)if(i==k)word=uWords[i];
      float at=mod(cell.x+cell.y*3.,word.y+1.);
      index=at<word.y?word.x+at:0.;
    }
  }
  vec3 hue=rgb/max(max(rgb.r,rgb.g),max(rgb.b,.03));
  hue=mix(vec3(dot(hue,vec3(.2126,.7152,.0722))),hue,uSaturation);
  vec3 base=uRampCount>1.5?rampAt(tone):uInk;
  vec3 ink=mix(base*mix(1.,.3+.7*tone,uRampCount>1.5?0.:uShade),clamp(hue*(.38+.62*tone),0.,1.),uSourceColor);
  // Scatter, text and inlay carry the tone in the ink's strength, which the pixel pass reads back as opacity or tile shade.
  if(uOrder>1.5||(uOrder>.5&&uMark==0)||uMark==17)ink=mix(uInk,hue,uSourceColor)*tone;
  vec3 lifted=uHighlightAuto>.5?ink/max(max(ink.r,ink.g),max(ink.b,.06)):uHighlight;
  ink=mix(ink,lifted,wake*.7);
  if(spot>0.)ink=mix(ink,clamp(rgb/max(max(rgb.r,rgb.g),max(rgb.b,.08))*(.45+.55*tone),0.,1.),spot);
  float underAlpha=max(uBackground.a,min(1.,max(glow.r,max(glow.g,glow.b))));
  vec3 under=min(uBackground.rgb*uBackground.a+glow,vec3(underAlpha));
  // Glyphs keep their atlas index, exact in 8 bits; the other marks keep the tone, and empty where the charset is blank.
  outInk=vec4(ink,uMark==0||uMark==17?index/255.:uMark==1?(tone>.003?tone:0.):index>0.?max(tone,1./255.):0.);
  outUnder=vec4(under,underAlpha);
}`,fa=`#version 300 es
precision highp float;
precision highp sampler2D;
uniform sampler2D uAtlas, uCells, uUnder;
uniform vec2 uResolution, uCell, uPitch;
uniform float uColumns, uDotScale, uSourceColor;
uniform vec2 uDir;
uniform int uMark;
// Inlay accents: share of tiles, letter shuffle span, a seed that steps a few times a second, charset length.
uniform vec4 uInlay;
// Line marks: pitch in cell heights, weight, the share of cells that sparkle.
uniform vec4 uLine;
uniform vec4 uFade;
out vec4 outColor;
const float BAYER[16]=float[16](0.,8.,2.,10.,12.,4.,14.,6.,3.,11.,1.,9.,15.,7.,13.,5.);
uniform vec3 uRamp[6];
uniform float uRampCount;
// The gradient map: the tone run through the ramp's stops, evenly spaced, faintest first.
vec3 rampAt(float t){
  float x=clamp(t,0.,1.)*(uRampCount-1.);
  int i=int(min(floor(x),uRampCount-2.));
  vec3 a=uRamp[0],b=uRamp[1];
  for(int k=1;k<5;k++)if(k==i){a=uRamp[k];b=uRamp[k+1];}
  return mix(a,b,clamp(x-float(i),0.,1.));
}
// The Studio's print defaults: roughness .35, seed 7, registration .2 and its coral second ink. The screen angle is uDir (-35deg).
const float ROUGH=.35,SEED=7.;
const vec3 SECOND=vec3(.925,.404,.322);
float hash(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
// Coverage of a signed distance given in device pixels.
float cover(float d){return clamp(.5-d,0.,1.);}
float box(vec2 p,vec2 lo,vec2 hi){vec2 a=clamp(p-lo,0.,1.)*clamp(hi-p,0.,1.);return a.x*a.y;}
float disc(vec2 p,vec2 c,float r){return r>.05?cover(length(p-c)-r):0.;}
float ellipse(vec2 p,vec2 c,vec2 r,float a){vec2 d=p-c;d=vec2(cos(a)*d.x+sin(a)*d.y,-sin(a)*d.x+cos(a)*d.y);float k=length(d/r);return cover((k-1.)*min(r.x,r.y));}
// World-anchored parallel cuts across direction d: period and width in cell heights, so lines run on from cell to cell.
float cuts(vec2 w,vec2 d,float period,float width,float px){
  if(width<=0.)return 0.;
  float proj=dot(vec2(-d.y,d.x),w);
  return cover((abs(fract(proj/period+.5)-.5)*period-width*.5)*px);
}
// Lays an ink over what is already down, multiplying where they overlap, as transparent inks do on paper.
void lay(inout vec3 rgb,inout float a,vec3 c,float k){
  float next=a+k*(1.-a);
  rgb=next>0.?(rgb*a*(1.-k)+mix(c,rgb*c,a)*k)/next:c;
  a=next;
}
void main(){
  vec2 DIR=uDir;
  vec2 frag=vec2(gl_FragCoord.x,uResolution.y-gl_FragCoord.y);
  // The pitch is the atlas cell, or a fractional one under cellFit 'fill', where each glyph sits centred in its stretched cell.
  vec2 cell=floor(frag/uPitch);
  vec4 ink=texelFetch(uCells,ivec2(cell),0),under=texelFetch(uUnder,ivec2(cell),0);
  vec2 local=frag-cell*uPitch;
  float coverage;
  vec3 rgb=ink.rgb;
  // Scatter and inlay: the cell's strength, read back from its ink, and the ink itself at full strength.
  float strength=1.;
  if(uFade.w>.5){
    float top=max(rgb.r,max(rgb.g,rgb.b));
    strength=uSourceColor>.5?top:clamp(top/max(max(uFade.r,max(uFade.g,uFade.b)),.004),0.,1.);
    rgb=uSourceColor>.5?rgb/max(top,.004):uFade.rgb;
  }
  if(uMark==0||uMark==17){
    float index=floor(ink.a*255.+.5);
    // Inlay shuffle: every tiled cell takes a letter from the upper charset, traded for a neighbour a few times a second, so a
    // tiled body flickers through its letters rather than banding by tone; the tile's shade still carries the tone.
    float hs=hash(cell*.917+uInlay.z*1.37);
    if(uMark==17&&uInlay.y>0.&&index>0.&&(index>=uInlay.w*.62||strength>=.2))index=clamp(max(index,ceil(uInlay.w*.62)+1.)+floor((hs-.5)*(2.*uInlay.y+1.)),ceil(uInlay.w*.62),uInlay.w-1.);
    ivec2 tile=ivec2(int(mod(index,uColumns)),int(floor(index/uColumns)));
    vec2 texel=floor(local-floor((uPitch-uCell)*.5));
    coverage=all(greaterThanEqual(texel,vec2(0.)))&&all(lessThan(texel,uCell))?texelFetch(uAtlas,tile*ivec2(uCell)+ivec2(texel),0).a:0.;
    if(uMark==17){
      // Inlay: a gapped tile in the ink, lighter the denser the cell, with its character set into it in a darker shade. Faint
      // cells keep only the character, so a shape's edge frays into specks; empty cells show a hairline grid.
      vec2 p=local+.5;
      float gap=max(1.,floor(min(uPitch.x,uPitch.y)*.08+.5));
      float plate=index>0.?smoothstep(.2,.32,strength)*box(p,vec2(0.),uPitch-gap):0.;
      // Tile and letter are the ink at two strengths over whatever ground lies below, so the inlay reads on light and dark pages:
      // the tile strengthens with the tone and the letter is cut back toward the ground.
      float face=(.18+.8*smoothstep(.05,.8,strength))*plate;
      // With shuffle on, tiles also vary a little in shade, as worn inlay does.
      if(uInlay.y>0.)face*=.8+.34*hs;
      float speck=coverage*min(1.,strength*6.)*(1.-plate);
      float grid=index>0.?0.:(1.-box(p,vec2(0.),uPitch-1.))*.035;
      float a=mix(face,face*.22,coverage*plate)+speck;
      // Accents: a few lit tiles carry a coloured letter, a tinted tile or a white glint, picked afresh with the seed.
      float ha=hash(cell*1.31+uInlay.z*.71+vec2(7.3,1.9));
      if(plate>0.&&ha<uInlay.x){
        float pick=hash(cell+uInlay.z*2.11+vec2(3.1,8.7));
        vec3 hue=pick<.16?vec3(.86,.27,.27):pick<.3?vec3(.92,.55,.2):pick<.42?vec3(.9,.78,.25):pick<.58?vec3(.35,.72,.38):pick<.72?vec3(.3,.72,.8):pick<.84?vec3(.32,.42,.92):vec3(.66,.42,.86);
        float kind=ha/uInlay.x;
        if(kind<.55){float k=coverage*plate;rgb=mix(rgb,hue,k);a=mix(a,1.,k);}
        else if(kind<.88){rgb=mix(rgb,hue,.55);}
        else{float k=coverage*plate;rgb=mix(rgb,vec3(1.),1.-k);a=mix(max(a,.96),face*.3,k);}
      }
      coverage=a>0.?a:grid;
    } else coverage*=strength;
  } else if(uMark==1){
    // Halftone: dot area follows tone, so midtones read true; edges are antialiased to one device pixel.
    float r=sqrt(ink.a)*min(uPitch.x,uPitch.y)*.5*uDotScale;
    coverage=ink.a>.003?clamp(r-length(local-uPitch*.5)+.5,0.,1.):0.;
  } else if(ink.a<=0.){
    coverage=0.;
  } else {
    float tone=ink.a,side=min(uPitch.x,uPitch.y);
    vec2 q=local/uPitch,c=uPitch*.5,p=local+.5;
    // Tiles fade with the tone in one ink, as the Studio's do; in source colour the colour already carries it.
    float fade=uSourceColor>.5?1.:tone,gap=max(.5,uPitch.x*.06),grain=hash(cell+SEED);
    vec2 w=(cell+q)*uPitch/uPitch.y;
    if(uMark==2)coverage=fade;
    else if(uMark==3)coverage=box(p,vec2(0.),uPitch-gap)*fade;
    else if(uMark==4){
      // Lego: a gapped brick, lit from above, with a raised stud ringed by its shadow.
      coverage=box(p,vec2(0.),uPitch-gap)*fade;
      rgb*=1.06-.14*q.y;
      float r=side*.28,d=length(local-c)-r,lit=clamp(dot(c-local,vec2(.6,.8))/r,-1.,1.);
      rgb=mix(rgb,mix(rgb,vec3(1.),.2+.12*lit),cover(d));
      rgb=mix(rgb,rgb*.72,cover(abs(d)-max(.5,side*.04)));
    } else if(uMark==5){
      // Voxel: an isometric cube; top, left and right faces at full, .72 and .42 strength.
      float h=.5*abs(q.x-.5);
      coverage=cover(-min(q.y-h,1.-h-q.y)*uPitch.y)*cover(-min(q.x,1.-q.x)*uPitch.x);
      coverage*=mix(q.x<.5?.72:.42,1.,cover((q.y-(.5-h))*uPitch.y))*fade;
    } else if(uMark==6){
      // Disco: a gapped mirror tile, its upper facet catching light and its lower in shade.
      coverage=box(p,vec2(0.),uPitch-gap)*fade;
      rgb=q.y<.35?mix(rgb,vec3(1.),.1+grain*.25):q.y>.65?rgb*.75:rgb;
    } else if(uMark==18){
      // Tick: a printed glow. A smooth wash carries the light; over it every cell holds one short upright tick whose strength
      // steps through four levels by a 4x4 ordered threshold, so the mid tones read as a crisp dither of ticks that brightens
      // toward the light and melts into the wash at its core. With a ramp the wash runs through it and the ticks sit a step up.
      ivec2 b=ivec2(mod(cell,4.));
      float th=(BAYER[b.y*4+b.x]+.5)/16.;
      float tw=max(1.,floor(uPitch.x*.28+.5)),tl=max(2.,floor(uPitch.y*.46+.5));
      vec2 lo=floor(c-vec2(tw,tl)*.5);
      float bar=box(p,lo,lo+vec2(tw,tl));
      float lvl=clamp(floor(tone*4.+th)/4.,0.,1.);
      float melt=1.-smoothstep(.7,.96,tone);
      float at=bar*melt*(.42+.58*lvl);
      bool ramped=uRampCount>1.5&&uSourceColor<.5;
      float aw=ramped?pow(smoothstep(.08,.88,tone),1.4):tone*tone*.92;
      vec3 W=ramped?rampAt(tone):rgb,T=ramped?rampAt(min(1.,lvl+.38)):rgb;
      float a=at+aw*(1.-at);
      rgb=a>0.?(T*at+W*aw*(1.-at))/a:W;
      coverage=a;
    } else if(uMark==19){
      // Bayer: one gapped square a cell, on or off by a 4x4 ordered threshold at two strengths, so a picture steps through
      // empty, half and full squares in the brand's tones, as pixel-dithered art does.
      ivec2 b=ivec2(mod(cell,4.));
      float th=(BAYER[b.y*4+b.x]+.5)/16.,g=max(1.,floor(min(uPitch.x,uPitch.y)*(1.-uDotScale)+.5));
      float lvl=tone>.5+th*.5?1.:tone>th*.5?.5:0.;
      // An empty cell keeps a small faint square, so the ground reads as a dot grid that the picture fills.
      vec2 d=floor(c-max(1.,floor(min(uPitch.x,uPitch.y)*.3))*.5);
      coverage=lvl>0.?box(p,vec2(0.),uPitch-g)*lvl:box(p,d,d+max(1.,floor(min(uPitch.x,uPitch.y)*.3)))*.35;
    } else if(uMark==7){
      // Dither: an ordered 4x4 Bayer screen at about five dots a cell, lit where the cell's tone passes the threshold.
      ivec2 b=ivec2(mod(floor(frag/max(1.,floor(side/5.))),4.));
      coverage=tone>(BAYER[b.y*4+b.x]+.5)/16.?1.:0.;
    } else if(uMark==8){
      // Hex: a flat-topped hexagon filling the cell.
      vec2 h=abs((local-c)/(uPitch*.49));
      coverage=cover(max(h.y-.866,h.x*.866+h.y*.5-.866)*side*.49)*fade;
    } else if(uMark==9){
      // LED: a round lamp with a soft halo and a specular glint, separated by an unlit matrix.
      float r=side*.39,d=length(local-c);
      coverage=max(cover(d-r),.3*exp(-pow(max(0.,d-r)/(side*.12),2.)))*fade;
      rgb=mix(rgb,vec3(1.),.35*disc(local,uPitch*vec2(.43,.4),side*.11));
    } else if(uMark==10){
      // CMYK: the cell's hue separated into offset cyan, magenta and yellow dots, each sized by its share of the tone. The
      // key screen carries the neutral share in the ink's own lightness, since a light ink on a dark page has no black.
      float top=max(rgb.r,max(rgb.g,rgb.b)),low=min(rgb.r,min(rgb.g,rgb.b));
      vec3 cmy=(top-rgb)/max(top,.001);
      float a=0.;vec3 col=vec3(1.);
      lay(col,a,vec3(top),disc(local,c,side*.48*sqrt(tone*low/max(top,.001))));
      lay(col,a,vec3(0.,1.,1.),disc(local,uPitch*vec2(.36,.36),side*.48*sqrt(tone*cmy.x)));
      lay(col,a,vec3(1.,0.,1.),disc(local,uPitch*vec2(.64,.36),side*.48*sqrt(tone*cmy.y)));
      lay(col,a,vec3(1.,1.,0.),disc(local,uPitch*vec2(.5,.66),side*.48*sqrt(tone*cmy.z)));
      rgb=col;coverage=a;
    } else if(uMark==11||uMark==16){
      // Stipple and pointillism: four jittered marks a cell, their size following the tone.
      coverage=0.;vec3 col=rgb;
      for(int m=0;m<4;m++){
        vec2 o=vec2(float(m%2),float(m/2));
        float j=hash(cell*2.+o+SEED),jy=hash(cell+o*11.+SEED+1.);
        vec2 at=((o+.5)/2.+(vec2(j,jy)-.5)*ROUGH*.28)*uPitch;
        float r=min(min(min(at.x,uPitch.x-at.x),min(at.y,uPitch.y-at.y)),side*min(.245,.21*sqrt(tone)*(1.-ROUGH*j*.35)));
        float k=uMark==11?disc(local,at,r):ellipse(local,at,vec2(r,r*.64),j*3.14159);
        if(uMark==16&&k>coverage)col=uSourceColor>.5?clamp(rgb+(j-.5)*ROUGH*.25*vec3(1.,-.4,-1.),0.,1.):rgb*(1.+(j-.5)*ROUGH*.5);
        coverage=max(coverage,k);
      }
      rgb=col;
    } else if(uMark==12||uMark==13){
      // Engraving and crosshatch: parallel cuts whose weight follows the tone; crossings join only in the darker tones.
      float cv=tone*(1.-ROUGH*grain*.3),px=uPitch.y,P=uLine.x,W=uLine.y*.72*P;
      coverage=cuts(w,DIR,P,min(.94*P,W*cv),px);
      if(uMark==13){
        coverage=max(coverage,cuts(w,vec2(-DIR.y,DIR.x),P,min(.94*P,W*max(0.,cv*1.5-.3)),px)*step(.2,cv));
        coverage=max(coverage,cuts(w,normalize(DIR+vec2(-DIR.y,DIR.x)),P,min(.94*P,W*max(0.,cv*2.-1.2)),px)*step(.6,cv));
      }
      // Sparkle: now and then a lit cell catches a small bright square, picked afresh a few times a second.
      if(uLine.z>0.&&tone>.2&&hash(cell*1.7+uInlay.z*.53)<uLine.z){float sq=max(1.,floor(side*.3+.5));vec2 lo=floor(c-sq*.5);float k=box(p,lo,lo+sq);coverage=max(coverage,k);rgb=mix(rgb,vec3(1.),k*.6);}
    } else if(uMark==14){
      // Woodblock: broad carved bands in five stepped weights, their edges wavering along the grain.
      float cv=ceil(tone*(1.-ROUGH*grain*.3)*5.)/5.,width=min(.94,.72*cv);
      float proj=dot(vec2(-DIR.y,DIR.x),w),line=floor(proj+.5),along=dot(DIR,w);
      float cut=sin(along*5.3+line*1.9+SEED)*.5+sin(along*13.1+line)*.25;
      coverage=cover((abs(proj-line)-width*.5*(1.+ROUGH*cut*.5))*uPitch.y);
    } else if(uMark==15){
      // Risograph: two offset screens, the main ink and the coral second ink, misregistered along the screen angle.
      float split=uSourceColor>.5?clamp(.5+(rgb.r-rgb.b)*.5,0.,1.):.5,r=side*min(.48,.44*sqrt(tone));
      float a=0.;vec3 col=rgb;
      lay(col,a,rgb,disc(local,c,r*sqrt(.35+(1.-split)*.65)));
      lay(col,a,SECOND,disc(local,c+DIR*.2*.38*side,r*sqrt(.3+split*.7)*(1.-ROUGH*hash(cell+SEED+13.)*.3)));
      rgb=col;coverage=a;
    } else coverage=0.;
  }
  outColor=vec4(rgb*coverage+under.rgb*(1.-coverage),coverage+under.a*(1.-coverage));
}`,Xt=`#version 300 es
precision highp float;
precision highp sampler2D;
uniform vec2 uTexel;
out vec4 outColor;
vec2 here(){return gl_FragCoord.xy*uTexel;}
`,Ja=Xt+`
uniform sampler2D uVelocity;
uniform vec2 uFrom, uTo, uForce;
uniform float uAspect, uRadius;
float segment(vec2 p,vec2 a,vec2 b){vec2 pa=p-a,ba=b-a;float h=clamp(dot(pa,ba)/max(dot(ba,ba),1e-8),0.,1.);return length(pa-ba*h);}
void main(){
  vec2 uv=here(),scale=vec2(uAspect,1.);
  float d=segment(uv*scale,uFrom*scale,uTo*scale);
  outColor=vec4(texture(uVelocity,uv).xy+uForce*exp(-d*d/(uRadius*uRadius)),0.,1.);
}`,Za=Xt+`
uniform sampler2D uVelocity;
void main(){
  vec2 uv=here();
  float l=texture(uVelocity,uv-vec2(uTexel.x,0.)).y,r=texture(uVelocity,uv+vec2(uTexel.x,0.)).y;
  float t=texture(uVelocity,uv+vec2(0.,uTexel.y)).x,b=texture(uVelocity,uv-vec2(0.,uTexel.y)).x;
  outColor=vec4(.5*(r-l-t+b),0.,0.,1.);
}`,ei=Xt+`
uniform sampler2D uVelocity, uCurl;
uniform float uStrength, uDt;
void main(){
  vec2 uv=here();
  float l=texture(uCurl,uv-vec2(uTexel.x,0.)).x,r=texture(uCurl,uv+vec2(uTexel.x,0.)).x;
  float t=texture(uCurl,uv+vec2(0.,uTexel.y)).x,b=texture(uCurl,uv-vec2(0.,uTexel.y)).x,c=texture(uCurl,uv).x;
  vec2 force=.5*vec2(abs(t)-abs(b),abs(r)-abs(l));
  force=force/(length(force)+1e-4)*uStrength*c;
  force.y=-force.y;
  outColor=vec4(clamp(texture(uVelocity,uv).xy+force*uDt,-1000.,1000.),0.,1.);
}`,ti=Xt+`
uniform sampler2D uVelocity;
void main(){
  vec2 uv=here(),c=texture(uVelocity,uv).xy;
  float l=texture(uVelocity,uv-vec2(uTexel.x,0.)).x,r=texture(uVelocity,uv+vec2(uTexel.x,0.)).x;
  float t=texture(uVelocity,uv+vec2(0.,uTexel.y)).y,b=texture(uVelocity,uv-vec2(0.,uTexel.y)).y;
  if(uv.x-uTexel.x<0.)l=-c.x;
  if(uv.x+uTexel.x>1.)r=-c.x;
  if(uv.y+uTexel.y>1.)t=-c.y;
  if(uv.y-uTexel.y<0.)b=-c.y;
  outColor=vec4(.5*(r-l+t-b),0.,0.,1.);
}`,ni=Xt+`
uniform sampler2D uSource;
uniform float uAmount;
void main(){outColor=vec4(texture(uSource,here()).x*uAmount,0.,0.,1.);}`,ri=Xt+`
uniform sampler2D uPressure, uDivergence;
void main(){
  vec2 uv=here();
  float l=texture(uPressure,uv-vec2(uTexel.x,0.)).x,r=texture(uPressure,uv+vec2(uTexel.x,0.)).x;
  float t=texture(uPressure,uv+vec2(0.,uTexel.y)).x,b=texture(uPressure,uv-vec2(0.,uTexel.y)).x;
  outColor=vec4((l+r+b+t-texture(uDivergence,uv).x)*.25,0.,0.,1.);
}`,oi=Xt+`
uniform sampler2D uPressure, uVelocity;
void main(){
  vec2 uv=here();
  float l=texture(uPressure,uv-vec2(uTexel.x,0.)).x,r=texture(uPressure,uv+vec2(uTexel.x,0.)).x;
  float t=texture(uPressure,uv+vec2(0.,uTexel.y)).x,b=texture(uPressure,uv-vec2(0.,uTexel.y)).x;
  outColor=vec4(texture(uVelocity,uv).xy-vec2(r-l,t-b),0.,1.);
}`,ai=Xt+`
uniform sampler2D uVelocity;
uniform float uDt, uDissipation;
void main(){
  vec2 uv=here();
  vec2 back=uv-uDt*texture(uVelocity,uv).xy*uTexel;
  outColor=vec4(texture(uVelocity,back).xy/(1.+uDissipation*uDt),0.,1.);
}`,Tn=new Set,Ht=0,Kr=0,Jo=null,sn=[],kn=0,Wn=1,rr=0,Zo=0;function ii(e){Ht=0,kn&&e>kn&&(sn.push(e-kn),sn.length>120&&sn.shift()),kn=e,Kr=performance.now();let r=[...Tn];Tn.clear();for(let o of r)try{o(e)}catch(a){typeof console<"u"&&console.error(a)}_t?.endFrame(e);let t=performance.now()-Kr;if(rr=.9*rr+.1*t,e-Zo>500){Zo=e;let o=da(),a=!!_t?.overloaded;(rr>.5*o||a)&&Wn<3?Wn++:rr<.2*o&&!a&&Wn>1&&Wn--}Tn.size||(kn=0)}var li=()=>Wn;function dr(e){Tn.add(e),Ht&&Jo!==requestAnimationFrame&&(Ht=0),Ht||(Jo=requestAnimationFrame,Ht=requestAnimationFrame(ii))}function mr(e){Tn.delete(e),!Tn.size&&Ht&&(cancelAnimationFrame(Ht),Ht=0,kn=0)}function da(){if(sn.length<20)return 1e3/60;let e=[...sn].sort((r,t)=>r-t);return Math.min(1e3/60,Math.max(1e3/360,e[Math.floor(.2*e.length)]))}var Vn=new Set,Zr=new Set,eo=new Set,to=new Set,no=new Set,Xr=!1,ea=null,or=null,ar=null,qn=null,ta=e=>{let r=null;for(let t of Vn){if(t.target===window){(!t.near||t.near()||t.inside)&&t.move(e);continue}r??(r=e.composedPath()),r.includes(t.target)?(t.inside=!0,t.move(e)):t.inside&&(t.inside=!1,t.leave())}},si=()=>{for(let e of Vn)e.inside=!1,e.leave()},ci=()=>{for(let e of[...Zr])e()},ui=()=>{for(let e of[...eo])e()},na=()=>{for(let e of[...to])e()},hi=e=>{for(let r of[...no])r(e)};function ra(){let e=Vn.size+Zr.size+eo.size+to.size+no.size>0;if(typeof document>"u"||(ea!==document&&(Xr=!1,ea=document,or=ar=null,qn=null),e===Xr))return;Xr=e;let r=e?"addEventListener":"removeEventListener";if(typeof window<"u"&&(window[r]?.("pointermove",ta,{capture:!0,passive:!0}),window[r]?.("pointerdown",ta,{capture:!0,passive:!0})),document[r]?.("pointerleave",si),document[r]?.("visibilitychange",ci),(typeof document>"u"?void 0:document.fonts)?.[r]?.("loadingdone",hi),or??(or=typeof matchMedia=="function"?matchMedia("(prefers-reduced-motion: reduce)"):null),ar??(ar=typeof matchMedia=="function"?matchMedia("(prefers-color-scheme: dark)"):null),or?.[r]?.("change",ui),ar?.[r]?.("change",na),e){qn??(qn=typeof MutationObserver=="function"?new MutationObserver(na):null);for(let t of[document.documentElement,document.body])t&&qn?.observe(t,{attributes:!0,attributeFilter:["class","data-theme","data-mode","style"]})}else qn?.disconnect()}var Rn=(e,r)=>(e.add(r),ra(),()=>{e.delete(r)&&ra()});function fi(e){let r=e.target;if(typeof window>"u"||r===window||typeof document>"u")return Rn(Vn,e);let t=r,o=t.getRootNode?.();if(t.ownerDocument===document&&(!o||o===document))return Rn(Vn,e);let a=e.move,s=()=>e.leave();return t.addEventListener("pointermove",a,{passive:!0}),t.addEventListener("pointerdown",a,{passive:!0}),t.addEventListener("pointerleave",s),()=>{t.removeEventListener("pointermove",a),t.removeEventListener("pointerdown",a),t.removeEventListener("pointerleave",s)}}var di=e=>Rn(Zr,e),mi=e=>Rn(eo,e),ma=e=>Rn(to,e),zn=new Map,bn=null,Wr=new Map,pa=e=>r=>{for(let t of r)for(let o of[...e.get(t.target)??[]])o(t)},ga=(e,r,t)=>{let o=e.get(r);return o?(o.add(t),!1):(e.set(r,new Set([t])),!0)},va=(e,r,t)=>{let o=e.get(r);return!(!o?.delete(t)||o.size)&&(e.delete(r),!0)};function Vr(e,r){return typeof ResizeObserver!="function"?()=>{}:(bn??(bn=new ResizeObserver(pa(zn))),ga(zn,e,r)?bn.observe(e):queueMicrotask(()=>{zn.get(e)?.has(r)&&r({target:e})}),()=>{va(zn,e,r)&&bn?.unobserve(e),zn.size||(bn?.disconnect(),bn=null)})}var pi=268435456,ir=[1,.85,.7,.58,.5],gi=class{constructor(){this.lost=!1,this.level=0,this.programs=new Map,this.atlases=new Map,this.vertex=null,this.vao=null,this.clients=new Set,this.parallel=null,this.timer=null,this.queries=[],this.open=null,this.drew=!1,this.gpuMs=[],this.cpuMs=[],this.changedAt=0,this.lostTimer=0,this.renderer="",this.overloaded=!1,this.onLost=e=>{e.preventDefault(),this.lost=!0,this.reset();for(let r of[...this.clients])r.lost();clearTimeout(this.lostTimer),this.lostTimer=setTimeout(()=>{if(this.lost){this.canvas.removeEventListener?.("webglcontextlost",this.onLost),this.canvas.removeEventListener?.("webglcontextrestored",this.onRestored);try{this.create()}catch{return}this.restored()}},1e3)},this.onRestored=()=>{clearTimeout(this.lostTimer),this.lost=!1,this.restored()},this.idleTimer=0,this.create()}create(){let e=null,r=null,t={alpha:!0,antialias:!1,depth:!1,stencil:!1,premultipliedAlpha:!0,preserveDrawingBuffer:!0,powerPreference:"high-performance"};if(typeof document<"u"&&(e=document.createElement("canvas"),r=e.getContext("webgl2",t)),!r&&typeof OffscreenCanvas=="function")try{e=new OffscreenCanvas(1,1),r=e.getContext("webgl2",t)}catch{r=null}if(!r||!e)throw new Error("WebGL2 is not available for the glyph field.");this.canvas=e,this.gl=r,this.lost=!1,e.width=e.height=1,this.parallel=r.getExtension("KHR_parallel_shader_compile"),this.timer=r.getExtension("EXT_disjoint_timer_query_webgl2");let o=r.getExtension("WEBGL_debug_renderer_info");this.renderer=String(r.getParameter(o?o.UNMASKED_RENDERER_WEBGL:r.RENDERER)??""),e.addEventListener?.("webglcontextlost",this.onLost),e.addEventListener?.("webglcontextrestored",this.onRestored);let a=!r.getExtension("EXT_color_buffer_float")&&!r.getExtension("EXT_color_buffer_half_float");this.program(ha(a)),this.program(fa)}restored(){for(let e of[...this.clients])e.restored()}reset(){this.programs.clear(),this.atlases.clear(),this.vertex=null,this.vao=null,this.queries=[],this.open=null,this.gpuMs=[],this.cpuMs=[]}join(e){this.clients.add(e),clearTimeout(this.idleTimer)}leave(e){this.clients.delete(e),this.clients.size?this.fit():(this.lost||(this.canvas.width=this.canvas.height=1,this.level=0),clearTimeout(this.idleTimer),this.idleTimer=setTimeout(()=>{this.clients.size||this.dispose()},3e3))}dispose(){if(clearTimeout(this.lostTimer),this.canvas.removeEventListener?.("webglcontextlost",this.onLost),this.canvas.removeEventListener?.("webglcontextrestored",this.onRestored),!this.lost)try{this.gl.getExtension("WEBGL_lose_context")?.loseContext()}catch{}this.reset(),_t===this&&(_t=null)}program(e){let r=this.programs.get(e);if(r)return r;let t=this.gl,o=(l,f)=>{let p=t.createShader(l);return t.shaderSource(p,f),t.compileShader(p),p};this.vertex??(this.vertex=o(t.VERTEX_SHADER,`#version 300 es
void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.-1.,0.,1.);}`));let a=t.createProgram(),s=o(t.FRAGMENT_SHADER,e);t.attachShader(a,this.vertex),t.attachShader(a,s),t.linkProgram(a);let u={program:a,locations:null,fragment:s};return this.programs.set(e,u),u}linked(e,r=!1){if(e.locations)return!0;let t=this.gl;if(!r&&this.parallel&&!t.getProgramParameter(e.program,this.parallel.COMPLETION_STATUS_KHR))return!1;if(!t.getProgramParameter(e.program,t.LINK_STATUS)){if(t.isContextLost())return!1;throw new Error(e.fragment&&t.getShaderInfoLog(e.fragment)||t.getProgramInfoLog(e.program)||"Glyph field program failed to link.")}let o={};for(let a=t.getProgramParameter(e.program,t.ACTIVE_UNIFORMS)-1;a>=0;a--){let s=t.getActiveUniform(e.program,a).name.replace(/\[0\]$/,"");o[s]=t.getUniformLocation(e.program,s)}return e.locations=o,!0}get canCompileInParallel(){return!!this.parallel}vertexArray(){return this.vao??(this.vao=this.gl.createVertexArray())}atlas(e,r,t){let o=this.atlases.get(e);if(o)o.refs||(this.atlases.delete(e),this.atlases.set(e,o));else{let a=this.gl,s=a.createTexture();a.bindTexture(a.TEXTURE_2D,s);for(let[u,l]of[[a.TEXTURE_MIN_FILTER,a.NEAREST],[a.TEXTURE_MAG_FILTER,a.NEAREST],[a.TEXTURE_WRAP_S,a.CLAMP_TO_EDGE],[a.TEXTURE_WRAP_T,a.CLAMP_TO_EDGE]])a.texParameteri(a.TEXTURE_2D,u,l);o={key:e,texture:s,refs:0,final:!1,users:new Set,bytes:0},this.atlases.set(e,o),this.paintAtlas(o,r)}return o.refs++,o.users.add(t),o}hasAtlas(e){return this.atlases.has(e)}paintAtlas(e,r){let t=this.gl,{image:o,final:a}=r();t.bindTexture(t.TEXTURE_2D,e.texture),t.pixelStorei(t.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!1),t.pixelStorei(t.UNPACK_FLIP_Y_WEBGL,!1),t.texImage2D(t.TEXTURE_2D,0,t.RGBA8,t.RGBA,t.UNSIGNED_BYTE,o),e.bytes=o.width*o.height*4,e.final=a;for(let s of[...e.users])s()}releaseAtlas(e,r){e&&e.users.delete(r)&&(--e.refs>0||this.evictAtlases())}evictAtlases(){let e=[...this.atlases.values()].filter(t=>!t.refs),r=e.length-32;for(let t of e){if(r<=0&&!this.overBudget)break;r--,this.atlases.delete(t.key),this.lost||this.gl.deleteTexture(t.texture)}}fit(){if(this.lost)return;let e=1,r=1;for(let a of this.clients){let[s,u]=a.size();e=Math.max(e,s),r=Math.max(r,u)}let t=this.canvas,o=a=>256*Math.ceil(a/256);t.width*t.height>o(e)*o(r)*2&&(t.width=o(e),t.height=o(r))}get bytes(){let e=this.canvas.width*this.canvas.height*4*2;for(let r of this.clients)e+=r.bytes();for(let r of this.atlases.values())e+=r.bytes;return e}get overBudget(){return this.bytes>pi}get roomy(){return this.bytes<2281701376e-1}begin(e,r){let t=this.canvas;if(t.width<e||t.height<r){let o=a=>256*Math.ceil(a/256);t.width=Math.max(t.width,o(e)),t.height=Math.max(t.height,o(r))}if(!this.drew&&(this.drew=!0,this.timer&&!this.open&&this.queries.length<4)){let o=this.gl.createQuery();o&&(this.gl.beginQuery(this.timer.TIME_ELAPSED_EXT,o),this.open=o)}}present(e,r,t){e.globalCompositeOperation="copy",e.imageSmoothingEnabled=!1,e.drawImage(this.canvas,0,this.canvas.height-t,r,t,0,0,r,t)}endFrame(e){if(this.lost)return void(this.drew=!1);let r=this.gl,t=this.timer;if(this.drew&&(this.cpuMs.push(performance.now()-Kr),this.cpuMs.length>60&&this.cpuMs.shift(),t&&this.open&&(r.endQuery(t.TIME_ELAPSED_EXT),this.queries.push({query:this.open,frame:e}),this.open=null)),this.drew=!1,t){let o=r.getParameter(t.GPU_DISJOINT_EXT);for(;this.queries.length&&r.getQueryParameter(this.queries[0].query,r.QUERY_RESULT_AVAILABLE);){let{query:a}=this.queries.shift();o||(this.gpuMs.push(r.getQueryParameter(a,r.QUERY_RESULT)/1e6),this.gpuMs.length>60&&this.gpuMs.shift()),r.deleteQuery(a)}}this.adapt(e)}adapt(e){let r=da(),t=this.gpuMs.length>=5&&Math.min(...this.gpuMs.slice(-5))>1.5*r,o=this.gpuMs.length>=10||t?this.gpuMs:null,a;if(o)a=[...o].sort((u,l)=>u-l)[Math.floor(.75*o.length)]/r;else{if(sn.length<30||this.cpuMs.length<10)return;let u=sn.slice(-30).sort((f,p)=>f-p),l=[...this.cpuMs].sort((f,p)=>f-p)[this.cpuMs.length>>1];a=u[Math.floor(.75*u.length)]/r>1.6&&l<.5*r?1:.5}if(this.overloaded=a>.8&&this.atMinimum,e-this.changedAt<(a>.8?800:4e3))return;let s=this.level;if(a>2?s=ir.length-1:a>.8&&s<ir.length-1?s++:a<.3&&s>0&&s--,s!==this.level){this.level=s,this.changedAt=e,this.gpuMs=[],this.cpuMs=[];for(let u of[...this.clients])u.rescale()}}get scale(){return ir[this.level]}get atMinimum(){return this.level===ir.length-1}},_t=null,oa=!1;function ro(){if(_t||oa)return _t;try{_t=new gi}catch{oa=!0}return _t}var xa=()=>_t,ya=new WeakSet,Ma=e=>ya.has(e),vi=/^[\u1100-\u115f\u2e80-\ua4cf\uac00-\ud7a3\uf900-\ufaff\ufe30-\ufe4f\uff00-\uff60\uffe0-\uffe6]|^[\u{20000}-\u{3fffd}]/u,wa=e=>vi.test(e),xi=class{constructor(e,r,t){this.previous=null,this.peak=0,this.width=e,this.height=r,this.span=t??Math.min(e,r);let o=e*r;this.pixels=new Uint8Array(4*o),this.signal=new Float32Array(o),this.offsetX=new Float32Array(o),this.offsetY=new Float32Array(o),this.driftX=new Float32Array(o),this.driftY=new Float32Array(o),this.u=new Float32Array(o),this.v=new Float32Array(o),this.ink=new Float32Array(o),this.a=new Float32Array(o),this.b=new Float32Array(o),this.c=new Float32Array(o),this.pressure=new Float32Array(o),this.pressureNext=new Float32Array(o),this.divergence=new Float32Array(o),this.curl=new Float32Array(o)}get active(){return this.peak>2e-4}clear(){for(let e of[this.u,this.v,this.ink,this.a,this.b,this.c,this.pressure,this.pressureNext,this.divergence,this.curl,this.signal,this.pixels,this.offsetX,this.offsetY,this.driftX,this.driftY])e.fill(0);this.previous=null,this.peak=0}leave(){this.previous=null}move(e,r,t,o=performance.now()){if(!Number.isFinite(e+r+t+o))return;e=Math.max(0,Math.min(1,e)),r=Math.max(0,Math.min(1,r)),t=Math.max(.1,Math.min(1,t));let a=this.previous;if(this.previous={x:e,y:r,time:o},!a)return;let s=(e-a.x)*(this.width-1),u=(r-a.y)*(this.height-1),l=Math.hypot(s,u);if(l<.001)return;let f=this.span,p=o>a.time?Math.max(1/240,(o-a.time)/1e3):1/60,d=Math.min(12,l/f/p),x=1-Math.exp(-d/2.2),v=f*(.022+.075*t)*(.65+.95*x),w=Math.min(128,Math.max(1,Math.ceil(l/(.4*v)))),n=l/v*(.32+.22*x)/w,b=s/l,W=u/l,L=-W,z=b,oe=l*(2+18*x)/w;for(let M=0;M<w;M++){let _=(M+.5)/w,$=(a.x+(e-a.x)*_)*(this.width-1),se=(a.y+(r-a.y)*_)*(this.height-1),Fe=Math.max(1,Math.floor($-3*v)),Me=Math.min(this.width-2,Math.ceil($+3*v)),G=Math.max(1,Math.floor(se-3*v)),me=Math.min(this.height-2,Math.ceil(se+3*v));for(let ye=G;ye<=me;ye++)for(let A=Fe;A<=Me;A++){let D=((A-$)*b+(ye-se)*W)/v,B=((A-$)*L+(ye-se)*z)/v,Z=Math.exp(-D*D*.65-B*B*1.7),ae=ye*this.width+A;this.ink[ae]=1-(1-this.ink[ae])*Math.exp(-Z*n);let Be=1-B*B*.55,ge=D*B*.7;this.u[ae]=Math.max(-80,Math.min(80,this.u[ae]+(b*Be+L*ge)*Z*oe)),this.v[ae]=Math.max(-80,Math.min(80,this.v[ae]+(W*Be+z*ge)*Z*oe))}}this.peak=1}read(e,r,t){let o=0|(r=Math.max(.5,Math.min(this.width-1.5,r))),a=0|(t=Math.max(.5,Math.min(this.height-1.5,t))),s=r-o,u=t-a,l=a*this.width+o;return(e[l]*(1-s)+e[l+1]*s)*(1-u)+(e[l+this.width]*(1-s)+e[l+this.width+1]*s)*u}sample(e,r){return this.read(this.signal,e*(this.width-1),r*(this.height-1))}displacement(e,r,t){t[0]=this.read(this.offsetX,e*(this.width-1),r*(this.height-1)),t[1]=this.read(this.offsetY,e*(this.width-1),r*(this.height-1))}step(e){if(!this.active||!Number.isFinite(e))return;let r=Math.max(0,Math.min(.05,e)),t=this.width,o=this.height;for(;r>1e-7;){let a=Math.min(.016666666666666666,r);r-=a;let s=Math.exp(-1.9*a),u=Math.exp(-3.2*a);for(let f=1;f<o-1;f++)for(let p=1;p<t-1;p++){let d=f*t+p,x=Math.max(.5,Math.min(t-1.5,p-this.u[d]*a)),v=Math.max(.5,Math.min(o-1.5,f-this.v[d]*a)),w=0|x,n=0|v,b=x-w,W=v-n,L=n*t+w,z=(1-b)*(1-W),oe=b*(1-W),M=(1-b)*W,_=b*W;this.a[d]=(this.u[L]*z+this.u[L+1]*oe+this.u[L+t]*M+this.u[L+t+1]*_)*s,this.b[d]=(this.v[L]*z+this.v[L+1]*oe+this.v[L+t]*M+this.v[L+t+1]*_)*s,this.c[d]=(this.ink[L]*z+this.ink[L+1]*oe+this.ink[L+t]*M+this.ink[L+t+1]*_)*u}[this.u,this.a]=[this.a,this.u],[this.v,this.b]=[this.b,this.v],[this.ink,this.c]=[this.c,this.ink];for(let f=1;f<o-1;f++)for(let p=1;p<t-1;p++){let d=f*t+p;this.curl[d]=.5*(this.v[d+1]-this.v[d-1]-this.u[d+t]+this.u[d-t])}for(let f=1;f<o-1;f++)for(let p=1;p<t-1;p++){let d=f*t+p,x=Math.abs(this.curl[d+1])-Math.abs(this.curl[d-1]),v=Math.abs(this.curl[d+t])-Math.abs(this.curl[d-t]),w=Math.hypot(x,v)+1e-4,n=this.curl[d]*a*10,b=Math.hypot(this.u[d],this.v[d]);this.u[d]+=v/w*n,this.v[d]-=x/w*n;let W=Math.min(1,b/(Math.hypot(this.u[d],this.v[d])+1e-6));this.u[d]*=W,this.v[d]*=W,this.divergence[d]=-.5*(this.u[d+1]-this.u[d-1]+this.v[d+t]-this.v[d-t])}this.pressure.fill(0);for(let f=0;f<4;f++){for(let p=1;p<o-1;p++)for(let d=1;d<t-1;d++){let x=p*t+d;this.pressureNext[x]=.25*(this.divergence[x]+this.pressure[x-1]+this.pressure[x+1]+this.pressure[x-t]+this.pressure[x+t])}[this.pressure,this.pressureNext]=[this.pressureNext,this.pressure]}let l=0;for(let f=1;f<o-1;f++)for(let p=1;p<t-1;p++){let d=f*t+p;this.u[d]=Math.max(-80,Math.min(80,this.u[d]-.5*(this.pressure[d+1]-this.pressure[d-1]))),this.v[d]=Math.max(-80,Math.min(80,this.v[d]-.5*(this.pressure[d+t]-this.pressure[d-t]))),this.driftX[d]+=(3.6*this.u[d]-58*this.offsetX[d]-12*this.driftX[d])*a,this.driftY[d]+=(3.6*this.v[d]-58*this.offsetY[d]-12*this.driftY[d])*a,this.offsetX[d]=Math.max(-2,Math.min(2,this.offsetX[d]+this.driftX[d]*a)),this.offsetY[d]=Math.max(-2,Math.min(2,this.offsetY[d]+this.driftY[d]*a)),this.signal[d]=1-Math.exp(.06*-Math.hypot(this.u[d],this.v[d])-.16*this.ink[d]),l=Math.max(l,this.signal[d])}this.peak=l}if(this.active)for(let a=0;a<this.ink.length;a++){let s=Math.round(65535*Math.min(1,this.signal[a]));this.pixels[4*a]=s>>>8,this.pixels[4*a+1]=255&s,this.pixels[4*a+2]=Math.round(128+63.5*this.offsetX[a]),this.pixels[4*a+3]=Math.round(128+63.5*this.offsetY[a])}else this.clear()}};function Ue(e,r,t,o,a){if(!(a<1))for(let s=0;s<2;s++){for(let u=0;u<o;u++){let l=0,f=u*t;for(let p=-a;p<=a;p++)l+=e[f+Math.max(0,Math.min(t-1,p))];for(let p=0;p<t;p++)r[f+p]=l/(2*a+1),l+=e[f+Math.min(t-1,p+a+1)]-e[f+Math.max(0,p-a)]}for(let u=0;u<t;u++){let l=0;for(let f=-a;f<=a;f++)l+=r[Math.max(0,Math.min(o-1,f))*t+u];for(let f=0;f<o;f++)e[f*t+u]=l/(2*a+1),l+=r[Math.min(o-1,f+a+1)*t+u]-r[Math.max(0,f-a)*t+u]}}}var jr=new Float32Array(0);function ba(e,r,t,o,a){let s=r*t,u=a&&a.width===r&&a.height===t?a:{width:r,height:t,subject:new Float32Array(s),depth:new Float32Array(s),key:"none"},{subject:l,depth:f}=u,p=0;for(let n=0;n<s;n++)e[4*n+3]<250&&p++;let d=n=>(.2126*e[4*n]+.7152*e[4*n+1]+.0722*e[4*n+2])/255,x="none",v=0;if(p>.01*s)x="alpha";else if(o)x="mask";else{let n=0,b=0,W=0,L=Math.max(1,Math.round(.03*Math.min(r,t)));for(let z=0;z<t;z++)for(let oe=0;oe<r;oe++){if(oe>=L&&z>=L&&oe<r-L&&z<t-L)continue;let M=d(z*r+oe);n+=M,b+=M*M,W++}v=n/Math.max(1,W),Math.sqrt(Math.max(0,b/Math.max(1,W)-v*v))<.07&&(x="ground")}for(let n=0;n<s;n++){let b=e[4*n+3]/255,W=d(n),L=1;if(x==="alpha")L=b;else if(x==="ground"){let z=Math.max(0,Math.min(1,(Math.abs(W-v)-.035)/.12));L=z*z*(3-2*z)}l[n]=L*(o?Math.max(0,Math.min(1,o[n])):1),f[n]=W*b}u.key=x,jr.length<s&&(jr=new Float32Array(s));let w=jr;return Ue(l,w,r,t,Math.max(1,Math.round(.02*Math.min(r,t)))),Ue(f,w,r,t,Math.max(1,Math.round(.035*Math.min(r,t)))),u}var Hn=11,at=e=>Math.max(0,Math.min(1,e)),N=(e,r,t)=>{let o=at((t-e)/(r-e));return o*o*(3-2*o)};function xt(e,r,t=256){let o=0;for(let l=0;l<e.length;l++)e[l]>o&&(o=e[l]);if(o<=0)return 0;let a=new Uint32Array(t);for(let l=0;l<e.length;l++)a[Math.min(t-1,Math.floor(Math.max(0,e[l])/o*t))]++;let s=0,u=e.length*r;for(let l=0;l<t;l++)if(s+=a[l],s>=u)return(l+1)/t*o;return o}var yi=class{constructor(e){this.n=e,this.arrays=[],this.next=0}take(e){this.next===this.arrays.length&&this.arrays.push(new Float32Array(this.n));let r=this.arrays[this.next++];return e?r.set(e):r.fill(0),r}reset(){this.next=0}},lr=null;function ln(e,r,t,o,a){let s=2*a+1;for(let u=0;u<o;u++){let l=u*t,f=0;for(let p=-a;p<=a;p++)f+=e[l+Math.max(0,Math.min(t-1,p))];for(let p=0;p<t;p++)r[l+p]=f/s,f+=e[l+Math.min(t-1,p+a+1)]-e[l+Math.max(0,p-a)]}for(let u=0;u<t;u++){let l=0;for(let f=-a;f<=a;f++)l+=r[Math.max(0,Math.min(o-1,f))*t+u];for(let f=0;f<o;f++)e[f*t+u]=l/s,l+=r[Math.min(o-1,f+a+1)*t+u]-r[Math.max(0,f-a)*t+u]}}function Yr(e,r,t,o,a,s,u){let l=t*o,f=u.take(),p=u.take(r),d=u.take(e),x=u.take(),v=u.take();for(let w=0;w<l;w++)x[w]=r[w]*r[w],v[w]=r[w]*e[w];ln(p,f,t,o,a),ln(d,f,t,o,a),ln(x,f,t,o,a),ln(v,f,t,o,a);for(let w=0;w<l;w++){let n=(v[w]-p[w]*d[w])/(x[w]-p[w]*p[w]+s);x[w]=n,v[w]=d[w]-n*p[w]}ln(x,f,t,o,a),ln(v,f,t,o,a);for(let w=0;w<l;w++)e[w]=x[w]*r[w]+v[w]}function $r(e,r,t,o,a,s=2){for(let u=0;u<s;u++){for(let l=0;l<o;l++)for(let f=0;f<t;f++){let p=l*t+f,d=e[p];f>0&&(d=Math.max(d,Math.min(r[p],e[p-1]*a))),l>0&&(d=Math.max(d,Math.min(r[p],e[p-t]*a),f>0?Math.min(r[p],e[p-t-1]*a):0,f<t-1?Math.min(r[p],e[p-t+1]*a):0)),e[p]=d}for(let l=o-1;l>=0;l--)for(let f=t-1;f>=0;f--){let p=l*t+f,d=e[p];f<t-1&&(d=Math.max(d,Math.min(r[p],e[p+1]*a))),l<o-1&&(d=Math.max(d,Math.min(r[p],e[p+t]*a),f>0?Math.min(r[p],e[p+t-1]*a):0,f<t-1?Math.min(r[p],e[p+t+1]*a):0)),e[p]=d}}}function sr(e,r,t,o,a){for(let s=0;s<o;s++)for(let u=0;u<t;u++){let l=1;for(let f=Math.max(0,u-a);f<=Math.min(t-1,u+a);f++)l=Math.min(l,e[s*t+f]);r[s*t+u]=l}for(let s=0;s<o;s++)for(let u=0;u<t;u++){let l=1;for(let f=Math.max(0,s-a);f<=Math.min(o-1,s+a);f++)l=Math.min(l,r[f*t+u]);e[s*t+u]=l}}function Mi(e,r,t,o,a){let s=t*o,u=Math.min(t,o),l=a.take(),f=a.take(),p=a.take(),d=a.take(),x=a.take();for(let c=0;c<s;c++){let C=e[4*c+3]/255;x[c]=C,l[c]=r[4*c]/255*C,f[c]=r[4*c+1]/255*C,p[c]=r[4*c+2]/255*C,d[c]=(.299*e[4*c]+.587*e[4*c+1]+.114*e[4*c+2])/255*C}let v=a.take(),w=(c,C)=>{let E=a.take(c);return Ue(E,v,t,o,C),E},n=Math.max(2,Math.round(.04*u)),b=Math.max(n+2,Math.round(.12*u)),W=Math.max(2,Math.round(.05*u)),L=w(d,1),z=w(d,n),oe=w(d,b),M=a.take(),_=a.take(),$=a.take(),se=a.take(),Fe=a.take();for(let c=0;c<o;c++)for(let C=0;C<t;C++){let E=c*t+C;M[E]=Math.abs(d[E]-L[E]),_[E]=Math.abs(L[E]-z[E]),$[E]=Math.abs(z[E]-oe[E]),se[E]=Math.abs(d[c*t+Math.min(t-1,C+1)]-d[c*t+Math.max(0,C-1)]),Fe[E]=Math.abs(d[Math.min(o-1,c+1)*t+C]-d[Math.max(0,c-1)*t+C])}Ue(M,v,t,o,W),Ue(_,v,t,o,W),Ue($,v,t,o,W),Ue(se,v,t,o,2),Ue(Fe,v,t,o,2);let Me=Math.max(.01,xt(M,.9)+xt(_,.9)),G=w(l,1),me=w(f,1),ye=w(p,1),A=a.take(),D=a.take(),B=a.take(),Z=0;for(let c=0;c<s;c++){let C=G[c],E=me[c],ve=ye[c],ce=Math.max(C,E,ve),pe=ce-Math.min(C,E,ve);B[c]=ce,D[c]=ce>.001?pe/ce:0,Z+=pe;let Ce=0;pe>1e-4&&(Ce=ce===C?((E-ve)/pe+6)%6:ce===E?(ve-C)/pe+2:(C-E)/pe+4),A[c]=60*Ce}let ae=N(.02,.07,Z/s),Be=Math.max(2,Math.round(.06*o)),ge=new Float32Array(o);for(let c=0;c<o;c++){let C=0;for(let E=0;E<t;E++)C+=M[c*t+E]+_[c*t+E];ge[c]=C/t}let Ge=.5,Ne=0;for(let c=Math.max(Be,Math.round(.12*o));c<=Math.min(o-Be,Math.round(.88*o));c++){let C=0,E=0,ve=0,ce=0;for(let Q=0;Q<t;Q++){let ue=0,he=0,ie=0,Ie=0,be=0,Le=0;for(let ct=1;ct<=Be;ct++){let de=(c-ct)*t+Q,Ve=(c+ct-1)*t+Q;ue+=G[de],he+=me[de],ie+=ye[de],Ie+=G[Ve],be+=me[Ve],Le+=ye[Ve]}let Ke=(Math.abs(ue-Ie)+Math.abs(he-be)+Math.abs(ie-Le))/Be;C+=Ke,E+=Ke>.12?1:0}let pe=Math.max(2,Math.round(.15*o)),Ce=Math.max(0,c-pe),Te=Math.min(o,c+pe);for(let Q=Ce;Q<c;Q++)ve+=ge[Q];for(let Q=c;Q<Te;Q++)ce+=ge[Q];ve/=c-Ce,ce/=Te-c;let I=N(-.05,.3,(ce-ve)/(ce+ve+1e-4)),H=N(.08,.35,C/t)*(E/t)*I;H>Ne&&(Ne=H,Ge=c/o)}let Re=N(.15,.45,Ne),Xe=a.take(),V=a.take(),Ze=a.take();for(let c=0;c<s;c++)Xe[c]=Math.min(l[c],f[c],p[c]);sr(Xe,v,t,o,1),Ue(Xe,v,t,o,n);for(let c=0;c<s;c++)V[c]=_[c]+$[c];let it=0,ht=0,ft=0;for(let c=0;c<s;c++)it+=G[c],ht+=me[c],ft+=ye[c];it/=s,ht/=s,ft/=s;let et=w(G,n),lt=w(me,n),tt=w(ye,n),Ln=w(G,b),un=w(me,b),hn=w(ye,b);for(let c=0;c<s;c++){let C=Math.hypot(et[c]-it,lt[c]-ht,tt[c]-ft),E=Math.hypot(et[c]-Ln[c],lt[c]-un[c],tt[c]-hn[c]);Ze[c]=(C+1.5*E)*(.4+.6*D[c]*ae+.4*(1-ae))}let _e=a.take(),dt=a.take(),Pn=a.take(),De=a.take(),Wt=a.take(),kt=a.take(),qe=a.take(),Ye=a.take(),Vt=a.take(),jt=a.take();for(let c=0;c<o;c++)for(let C=0;C<t;C++)jt[c*t+C]=Math.abs(d[Math.min(o-1,c+1)*t+C]-d[Math.max(0,c-1)*t+C]);Ue(jt,v,t,o,1);for(let c=0;c<o;c++)for(let C=0;C<t;C++){let E=c*t+C,ve=(c+.5)/o,ce=A[E],pe=D[E]*ae,Ce=B[E],Te=M[E]+_[E],I=N(175,200,ce)*(1-N(250,275,ce))*N(.08,.25,pe),H=(1-N(45,65,ce)+N(290,330,ce))*N(.2,.45,pe)*N(.3,.55,Ce),Q=(1-N(.15,.35,pe))*N(.45,.7,Ce)*Re,ue=(1-N(.08,.2,Ce))*Re,he=Re>.3?1-N(Ge,Ge+.1,ve):1-N(.4,.8,ve),ie=1-N(.02,.06,Te),Ie=1-N(.03,.09,Te);dt[E]=Math.max(I*ie,.7*ue*(1-N(.008,.025,Te)),H*Ie*.9)*he,Pn[E]=Math.max(dt[E],Q*ie*he),_e[E]=c===0?dt[E]:0,De[E]=N(150,172,ce)*(1-N(232,250,ce))*N(.25,.45,pe),qe[E]=N(1.3,2.2,(se[E]+.004)/(Fe[E]+.004))*N(.35,.55,L[E])*(1-N(.1,.18,D[E]*ae))*N(.025,.07,Te)*N(.025,.045,jt[E]);let be=1-N(.18,.4,pe),Le=N(.55,.8,Ce)*N(.05,.12,Te);Wt[E]=Math.max(De[E],.85*be,.8*Le)}$r(_e,dt,t,o,.995,1),$r(_e,Pn,t,o,.8,1);let we=0;for(let c=0;c<s;c++)we+=_e[c];let st=we>.04*s&&Re>.3;if(st)for(let c=0;c<o;c++)for(let C=0;C<t;C++)De[c*t+C]*=N(Ge,Ge+.05,(c+.5)/o);if(st){let c=a.take(),C=a.take(),E=a.take();for(let I=0;I<s;I++)c[I]=.299*et[I]+.587*lt[I]+.114*tt[I];for(let I=0;I<o;I++)for(let H=0;H<t;H++)C[I*t+H]=L[Math.min(o-1,I+1)*t+H]-L[Math.max(0,I-1)*t+H];let ve=new Uint8Array(s);for(let I=1;I<o-1;I++)for(let H=0;H<t;H++){let Q=Math.abs(C[I*t+H]),ue=Q>.03;for(let he=-3;he<=3&&ue;he++)he&&I+he>=0&&I+he<o&&Math.abs(C[(I+he)*t+H])>Q&&(ue=!1);ve[I*t+H]=ue?1:0}let ce=(I,H,Q,ue=!0)=>{let he=et[H]+lt[H]+tt[H]+.05,ie=et[Q]+lt[Q]+tt[Q]+.05,Ie=Math.abs(et[H]/he-et[Q]/ie)+Math.abs(lt[H]/he-lt[Q]/ie)+Math.abs(tt[H]/he-tt[Q]/ie),be=Math.min(Math.abs(A[H]-A[Q]),360-Math.abs(A[H]-A[Q])),Le=Math.max(1-N(.1,.25,Ie),(1-N(15,35,be))*N(.15,.3,Math.min(D[H],D[Q]))),Ke=Math.max(N(2,3,(Fe[H]+.004)/(se[H]+.004))*N(.015,.04,M[H]+_[H])*N(.4,.55,M[H]/(M[H]+_[H]+1e-4)),1-N(.12,.25,c[H]));return Le*(ue?Ke:1)*(1-N(.82*c[Q]+.02,1.02*c[Q]+.05,c[H]))},pe=0,Ce=0;for(let I=Math.max(3,Math.round(o*Math.max(.25,Ge)));I<Math.round(.88*o);I++){let H=0;for(let ue=0;ue<t;ue++)(ve[(I-1)*t+ue]||ve[I*t+ue]||ve[(I+1)*t+ue])&&H++;if(H<.5*t)continue;let Q=0;for(let ue=I+1;ue<Math.min(o,2*I);ue++)for(let he=0;he<t;he++)Q+=ce(I,ue*t+he,(2*I-ue)*t+he);Q>Ce&&(Ce=Q,pe=I)}let Te=N(.05,.1,Ce/s);if(Te>0)for(let I=pe+1;I<Math.min(o,2*pe);I++)for(let H=0;H<t;H++){let Q=I*t+H;Ye[Q]=ce(pe,Q,(2*pe-I)*t+H)*Te,Vt[Q]=ce(pe,Q,(2*pe-I)*t+H,!1)*Te,E[Q]=Ye[Q]}Ue(E,v,t,o,1);for(let I=0;I<s;I++)Ye[I]=Math.max(Ye[I],E[I]),De[I]=Math.max(De[I],Ye[I])}let mt=w(De,b);for(let c=0;c<s;c++)De[c]*=N(.15,.35,mt[c]);let fn=w(De,n);for(let c=0;c<s;c++){De[c]*=1-.8*dt[c];let C=Math.min(Math.abs(A[c]-200),360-Math.abs(A[c]-200));kt[c]=N(.28,.45,D[c]*ae)*N(55,80,C)*(1-N(.3,.6,Vt[c]))}let Yt=w(kt,n);for(let c=0;c<s;c++)kt[c]=Math.max(kt[c]*(1-(1-N(.15,.3,Yt[c]))*N(.55,.7,B[c])*N(.5,.65,D[c])),1-x[c]),Wt[c]=Math.min(Math.max(Wt[c],.9*Vt[c]),Math.max(De[c],N(.25,.6,fn[c])))*(1-_e[c])*(1-kt[c]);$r(De,Wt,t,o,.97);let Tt=a.take(qe),$e=Math.max(2,Math.round(.12*o));for(let c=0;c<t;c++){let C=0;for(let E=-$e;E<=$e;E++)C+=qe[Math.max(0,Math.min(o-1,E))*t+c];for(let E=0;E<o;E++)Tt[E*t+c]=C/(2*$e+1),C+=qe[Math.min(o-1,E+$e+1)*t+c]-qe[Math.max(0,E-$e)*t+c]}Ue(Tt,v,t,o,1);for(let c=0;c<s;c++)qe[c]=N(.2,.45,Tt[c])*N(.2,.5,qe[c]+.5*Tt[c])*(1-_e[c]);Yr(_e,d,t,o,Math.max(2,Math.round(.04*u)),.002,a),Yr(De,d,t,o,Math.max(2,Math.round(.04*u)),.002,a),Yr(qe,d,t,o,Math.max(2,Math.round(.03*u)),.002,a),Ue(kt,v,t,o,1);for(let c=0;c<s;c++)_e[c]=N(.3,.7,_e[c])*x[c],qe[c]=N(.3,.7,qe[c])*x[c]*(1-_e[c]),De[c]=N(.3,.7,De[c])*(1-_e[c])*(1-qe[c])*(1-N(.15,.4,kt[c]));sr(_e,v,t,o,2),sr(De,v,t,o,2),sr(qe,v,t,o,1),Ue(_e,v,t,o,1),Ue(De,v,t,o,1),Ue(qe,v,t,o,1);let yt=1/Math.max(.02,xt(Ze,.97)),_n=1/Math.max(.01,xt(V,.9)),Bt=xt(Xe,.97),pt=xt(Xe,.1),nt=N(.06,.25,Bt-pt),rt=a.take();for(let c=0;c<o;c++)for(let C=0;C<t;C++){let E=c*t+C,ve=(C+.5)/t,ce=(c+.5)/o,pe=Math.max(_e[E],De[E]),Ce=M[E]+_[E]+$[E],Te=.6*at(((M[E]+.6*_[E])/(Ce+.004)-.25)/.55)+.4*at((M[E]+_[E])/Me),I=N(.04,.35,Ce/Me)*(1-pe),H=.55*at((Xe[E]-pt)/Math.max(.05,Bt-pt))+.25*(1-at(V[E]*_n))+.2*at(2*(ye[E]-G[E])+.3)*ae,Q=nt*N(.12,.35,z[E])*(.4+.6*Re),ue=Re*(ce<Ge?.45:.45+.55*N(0,1,(ce-Ge)/Math.max(.15,1-Ge)))+(1-Re)*(.5+.4*(ce-.5)),he=M[E]/(M[E]+_[E]+1e-4),ie=N(.2,.7,(M[E]+_[E])/Me)*(.35+.65*Re)*(1-pe),Ie=1-at(1.5*Math.hypot(1.2*(ve-.5),ce-.52)),be=at(Ze[E]*yt)*(.55+.45*Ie),Le=.3*I,Ke=.25*Q,ct=.12+.45*Re,de=.12*ie,Ve=.35*(1-.4*Re)*(1-pe);rt[E]=(Le*Te+Ke*(1-H)+ct*ue+de*at(1.6-1.6*he)+Ve*be+.04)/(Le+Ke+ct+de+Ve+.08)*(1-.85*_e[E])*(1-.45*De[E]*(1-Re))}let dn=ba(e,t,o);if(dn.key!=="none")for(let c=0;c<s;c++)rt[c]=.7*dn.subject[c]+.3*rt[c];return Ue(rt,v,t,o,Math.max(1,Math.round(.03*u))),(function(c,C,E,ve,ce,pe,Ce,Te,I){let H=ce*pe,Q=I.take(),ue=q=>(ln(q,Q,ce,pe,Ce),q),he=(q,St)=>{let Ot=I.take();for(let We=0;We<H;We++)Ot[We]=q[We]*St[We];return ue(Ot)},ie=ue(I.take(C)),Ie=ue(I.take(E)),be=ue(I.take(ve)),Le=ue(I.take(c)),Ke=he(C,C),ct=he(C,E),de=he(C,ve),Ve=he(E,E),Dn=he(E,ve),Mt=he(ve,ve),$t=he(C,c),Rt=he(E,c),In=he(ve,c),Kt=I.take(),At=I.take(),Qt=I.take(),mn=I.take();for(let q=0;q<H;q++){let St=$t[q]-ie[q]*Le[q],Ot=Rt[q]-Ie[q]*Le[q],We=In[q]-be[q]*Le[q],Gt=Ke[q]-ie[q]*ie[q]+Te,Nt=ct[q]-ie[q]*Ie[q],Qe=de[q]-ie[q]*be[q],Ft=Ve[q]-Ie[q]*Ie[q]+Te,qt=Dn[q]-Ie[q]*be[q],zt=Mt[q]-be[q]*be[q]+Te,Jt=Ft*zt-qt*qt,Zt=Qe*qt-Nt*zt,ut=Nt*qt-Qe*Ft,Un=Gt*zt-Qe*Qe,Bn=Nt*Qe-Gt*qt,On=Gt*Ft-Nt*Nt,pn=Gt*Jt+Nt*Zt+Qe*ut,gn=Math.abs(pn)>1e-12?1/pn:0;Kt[q]=(Jt*St+Zt*Ot+ut*We)*gn,At[q]=(Zt*St+Un*Ot+Bn*We)*gn,Qt[q]=(ut*St+Bn*Ot+On*We)*gn,mn[q]=Le[q]-Kt[q]*ie[q]-At[q]*Ie[q]-Qt[q]*be[q]}ue(Kt),ue(At),ue(Qt),ue(mn);for(let q=0;q<H;q++)c[q]=Kt[q]*C[q]+At[q]*E[q]+Qt[q]*ve[q]+mn[q]})(rt,G,me,ye,t,o,Math.max(2,Math.round(.07*u)),.004,a),{depth:rt,water:De,sky:_e,falls:qe}}function cr(e,r,t,o,a,s,u){if(r===s&&t===u)return e[a*s+o];let l=Math.max(0,Math.min(r-1,(o+.5)*r/s-.5)),f=Math.max(0,Math.min(t-1,(a+.5)*t/u-.5)),p=Math.min(r-2,Math.floor(l)),d=Math.min(t-2,Math.floor(f)),x=l-p,v=f-d;if(p<0||d<0)return e[Math.round(f)*r+Math.round(l)];let w=d*r+p,n=w+r;return(e[w]*(1-x)+e[w+1]*x)*(1-v)+(e[n]*(1-x)+e[n+1]*x)*v}var En=(e,r,t)=>{let o=Math.max(0,Math.min(1,(t-e)/(r-e)));return o*o*(3-2*o)},wi=class{constructor(e,r){this.base=40,this.mass=0,this.calm=0,this.drift=[0,0],this.fade=3,this.age=0,this.peak=0,this.front=0,this.live=!1,this.bins=new Uint32Array(64),this.spare=new Float32Array(0),this.cols=Math.max(3,0|e),this.rows=Math.max(3,0|r);let t=this.cols*this.rows;this.h=new Float32Array(t),this.p=new Float32Array(t),this.speed=new Float32Array(t).fill(1),this.damp=new Float32Array(t).fill(1),this.wall=new Float32Array(t),this.trace=new Float32Array(t)}clear(){this.h.fill(0),this.p.fill(0),this.trace.fill(0),this.live=!1,this.peak=0}drop(e,r,t=1,o=3){let{cols:a,rows:s,h:u,p:l}=this,f=Math.max(1,o),p=Math.ceil(3*f);for(let d=Math.max(1,Math.floor(r-p));d<Math.min(s-1,Math.ceil(r+p));d++)for(let x=Math.max(1,Math.floor(e-p));x<Math.min(a-1,Math.ceil(e+p));x++){let v=x-e,w=d-r,n=(v*v+w*w)/(f*f),b=t*(1-n)*Math.exp(-n),W=d*a+x;u[W]+=b,l[W]+=b}this.age=0,this.live=!0,this.peak=Math.max(this.peak,t),this.front=Math.max(this.front,t)}step(e,r=1){if(!(this.live&&e>0))return this.live;e=Math.min(.05,e),this.age+=e;let{cols:t,rows:o,speed:a,damp:s,wall:u,trace:l}=this,f=Math.max(0,this.base*r),p=0;for(let G=0;G<a.length;G++)a[G]>p&&(p=a[G]);let d=Math.max(1,Math.min(8,Math.ceil(f*e*Math.sqrt(p)/.6))),x=this.calm,v=e/d,w=f*v*(f*v),n=this.mass*v*v,b=this.h,W=this.p;for(let G=0;G<d;G++){for(let ye=1;ye<o-1;ye++)for(let A=1,D=ye*t+1;A<t-1;A++,D++){let B=b[D],Z=b[D-1]+b[D+1]+b[D-t]+b[D+t]-4*B,ae=l[D],Be=ae>.02?Math.max(0,1-Math.abs(B)/ae):0,ge=x*Be*Be*v,Ge=1-Math.min(.5,s[D]*v+ge);W[D]=(B+(B-W[D])*Ge+w*a[D]*Z-n*B)*(1-u[D])*(1-Math.min(.5,.5*ge))}let me=b;b=W,W=me}this.h=b,this.p=W;let L=this.drift[0]*e,z=this.drift[1]*e;(L||z)&&(this.carry(b,L,z),this.carry(W,L,z));for(let G=0;G<t;G++)b[G]=.5*b[t+G],b[(o-1)*t+G]=.5*b[(o-2)*t+G];for(let G=0;G<o;G++)b[G*t]=.5*b[G*t+1],b[G*t+t-1]=.5*b[G*t+t-2];let oe=Math.exp(-e*this.fade),M=0;for(let G=0;G<b.length;G++){let me=Math.abs(b[G]);me>M&&(M=me);let ye=l[G]*oe;l[G]=me>=ye?me:ye<1e-4?0:ye}this.peak=M;let _=this.bins.fill(0),$=.05*M,se=0;for(let G=0;G<b.length;G++)b[G]>$&&(_[Math.min(63,b[G]/M*64|0)]++,se++);let Fe=0,Me=63;for(;Me>0&&(Fe+=_[Me],!(Fe>=.08*se));Me--);return this.front=Math.max(.15*M,(Me+1)/64*M),!(M<.004)||(this.clear(),!1)}carry(e,r,t){let{cols:o,rows:a}=this;this.spare.length!==e.length&&(this.spare=new Float32Array(e.length));let s=this.spare;for(let u=0,l=0;u<a;u++){let f=Math.min(a-1.001,Math.max(0,u-t)),p=0|f,d=f-p;for(let x=0;x<o;x++,l++){let v=Math.min(o-1.001,Math.max(0,x-r)),w=0|v,n=v-w,b=p*o+w;s[l]=(e[b]*(1-n)+e[b+1]*n)*(1-d)+(e[b+o]*(1-n)+e[b+o+1]*n)*d}}e.set(s)}slope(e,r){let{h:t,cols:o}=this,a=t.length;return r[0]=.5*(t[Math.min(a-1,e+1)]-t[Math.max(0,e-1)]),r[1]=.5*(t[Math.min(a-1,e+o)]-t[Math.max(0,e-o)]),r}};function aa(e,r,t,o){let a=new Float32Array(e.length);for(let s=0;s<2;s++){let u=s?a:e,l=s?e:a;for(let f=0;f<t;f++)for(let p=0;p<r;p++){let d=0,x=0;for(let v=-o;v<=o;v++){let w=s?p:p+v,n=s?f+v:f;w<0||n<0||w>=r||n>=t||(d+=u[n*r+w],x++)}l[f*r+p]=d/x}}}var ur,bi=["none","flow","orb","drift","swell","caustics","contour","aurora","ripple","halo","interference","mesh","cascade","constellation"],pr=["glyph","dot","pixel","mosaic","lego","voxel","disco","dither","hex","led","cmyk","stipple","engraving","crosshatch","woodblock","risograph","pointillism","inlay","tick","bayer"],Ei=[{value:"fluid",label:"Fluid",description:"An ink-in-water wake that bends the image and swirls the characters."},{value:"lantern",label:"Lantern",description:"A soft light follows the pointer and lifts the characters it passes, without distortion."},{value:"trail",label:"Trail",description:"The Asciify Trail: in the wake, sparse characters fill in and dense ones open up, then settle. No distortion."},{value:"loupe",label:"Loupe",description:"A glass loupe glides after the pointer and magnifies the characters it covers."},{value:"reveal",label:"Reveal",description:"Under a soft spotlight the characters take the source image's own colours. Best over a photo or video in one ink."},{value:"none",label:"Off",description:"The field stays still under the pointer."}],ki={radius:.13,strength:.5,trail:.45,follow:12},Ti={strength:.55,radius:.45},Pt={radius:.075,force:1,dissipation:1.6,refraction:.03,glow:.55,resolution:128,curl:24},Ri={charset:" .,:-=+*#%@",cellSize:12,cellAspect:1,cellFit:"pixel",font:'ui-monospace, "SF Mono", Menlo, Consolas, monospace',fontWeight:500,glyphScale:.8,mark:"glyph",dotScale:.9,markAngle:-35,accents:0,shuffle:0,sample:"area",linePitch:.5,lineWeight:1,sparkle:0,textRepeat:"flow",glyphOrder:"tone",color:"ink",ink:"#f3ba32",highlight:"auto",background:"transparent",brightness:0,contrast:1,gamma:1,invert:!1,levels:"auto",blend:"auto",saturation:1.1,ramp:[],shade:.5,backdrop:0,fit:"cover",focus:{x:.5,y:.5},vignette:0,drift:0,scene:"flow",scale:1,clear:!1,speed:1,hover:"fluid",fluid:Pt,lantern:ki,trail:Ti,scope:"all",tap:"surface",maxPixelRatio:2,respectReducedMotion:!0},ne=(e,r,t,o)=>typeof e=="number"&&Number.isFinite(e)?Math.min(t,Math.max(r,e)):o,fr=(e,r)=>typeof e=="string"&&/^#([\da-f]{3}|[\da-f]{6})$/i.test(e.trim())?e.trim().toLowerCase():r,ia=/^[\u0020-\u007e\u00a0-\u02ff\u0370-\u0482\u048a-\u052f\u2010-\u20cf\u2100-\u2bff]*$/;function Dt(e){if(!ia.test(e)&&ur===void 0){let r=Intl.Segmenter;ur=r?new r(void 0,{granularity:"grapheme"}):null}return(ur&&!ia.test(e)?Array.from(ur.segment(e),r=>r.segment):Array.from(e)).filter(r=>r!==`
`&&r!=="\r"&&r!=="	").slice(0,256)}function Ai(e){let r=Dt(e).filter(t=>t.trim());return r.length>0&&2*r.filter(wa).length>r.length}var Si=(e,r,t)=>{let o=pr.includes(e)?e:r;return(o==="glyph"||o==="inlay")&&Ai(t)},Fi=(e,r)=>{if(!Array.isArray(e))return r;let t=e.map(o=>fr(o,"")).filter(Boolean).slice(0,6);return t.length>=2?t:[]};function Qr(e={},r=Ri){let t=typeof e.charset=="string"&&Dt(e.charset).length>=2?e.charset:r.charset,o=r.fluid||Pt,a=e.fluid===void 0?r.fluid:e.fluid,s=a!==!1&&(()=>{let x=a!==!0&&a?{...o,...a}:o;return{radius:ne(x.radius,.005,.5,Pt.radius),force:ne(x.force,0,8,Pt.force),dissipation:ne(x.dissipation,.05,20,Pt.dissipation),refraction:ne(x.refraction,0,.5,Pt.refraction),glow:ne(x.glow,0,2,Pt.glow),resolution:Math.round(ne(x.resolution,16,512,Pt.resolution)),curl:ne(x.curl,0,80,Pt.curl)}})(),u=bi.includes(e.scene)?e.scene:r.scene,l=!!e.clear&&typeof e.clear=="object"&&("element"in e.clear||"nodeType"in e.clear||"rects"in e.clear),f=e.clear===void 0||l?r.clear:e.clear,p=!!f&&{x:ne(f.x,-.5,1.5,.25),y:ne(f.y,-.5,1.5,.3),width:ne(f.width,0,2,.5),height:ne(f.height,0,2,.4),feather:ne(f.feather,.005,1,.12),shape:f.shape==="rect"?"rect":"ellipse"};return{charset:t,cellSize:ne(e.cellSize,1,96,r.cellSize),cellAspect:Si(e.mark,r.mark,t)?Math.max(1,ne(e.cellAspect,.3,2,r.cellAspect)):ne(e.cellAspect,.3,2,r.cellAspect),cellFit:e.cellFit==="fill"||e.cellFit==="pixel"?e.cellFit:r.cellFit,font:typeof e.font=="string"&&e.font.trim()?e.font:r.font,fontWeight:Math.round(ne(e.fontWeight,100,900,r.fontWeight)),glyphScale:ne(e.glyphScale,.3,1.6,r.glyphScale),mark:pr.includes(e.mark)?e.mark:r.mark,dotScale:ne(e.dotScale,.1,1.4,r.dotScale),markAngle:ne(e.markAngle,-360,360,r.markAngle),accents:ne(e.accents,0,.3,r.accents),shuffle:ne(e.shuffle,0,4,r.shuffle),sample:e.sample==="point"||e.sample==="area"?e.sample:r.sample,linePitch:ne(e.linePitch,.2,4,r.linePitch),lineWeight:ne(e.lineWeight,.2,3,r.lineWeight),sparkle:ne(e.sparkle,0,.05,r.sparkle),textRepeat:e.textRepeat==="row"||e.textRepeat==="flow"?e.textRepeat:r.textRepeat,glyphOrder:e.glyphOrder==="text"||e.glyphOrder==="tone"||e.glyphOrder==="scatter"?e.glyphOrder:r.glyphOrder,color:e.color==="source"||e.color==="ink"?e.color:r.color,ink:fr(e.ink,r.ink),highlight:e.highlight==="auto"?"auto":fr(e.highlight,r.highlight),ramp:Fi(e.ramp,r.ramp),background:e.background==="transparent"?"transparent":fr(e.background,r.background),brightness:ne(e.brightness,-1,1,r.brightness),contrast:ne(e.contrast,0,4,r.contrast),gamma:ne(e.gamma,.2,5,r.gamma),invert:typeof e.invert=="boolean"?e.invert:r.invert,levels:e.levels==="none"||e.levels==="auto"?e.levels:r.levels,blend:e.blend==="auto"||e.blend==="coarse"||e.blend==="on"||e.blend==="off"?e.blend:r.blend,saturation:ne(e.saturation,0,3,r.saturation),shade:ne(e.shade,0,1,r.shade),backdrop:ne(e.backdrop,0,1,r.backdrop),fit:e.fit==="contain"||e.fit==="cover"?e.fit:r.fit,focus:{x:ne(e.focus?.x,0,1,r.focus.x),y:ne(e.focus?.y,0,1,r.focus.y)},vignette:ne(e.vignette,0,1,r.vignette),drift:ne(e.drift,0,2,r.drift),scene:u,scale:ne(e.scale,.2,6,r.scale),clear:p,speed:ne(e.speed,0,5,r.speed),hover:Ei.some(x=>x.value===e.hover)?e.hover:r.hover,fluid:s,lantern:{radius:ne(e.lantern?.radius,.02,.6,r.lantern.radius),strength:ne(e.lantern?.strength,0,1.5,r.lantern.strength),trail:ne(e.lantern?.trail,0,3,r.lantern.trail),follow:ne(e.lantern?.follow,1,60,r.lantern.follow)},trail:{strength:ne(e.trail?.strength,0,1,r.trail.strength),radius:ne(e.trail?.radius,.1,1,r.trail.radius)},scope:e.scope===void 0?r.scope:(d=e.scope,d==="subject"||d==="outside"?d:"all"),tap:e.tap==="ring"||e.tap==="none"||e.tap==="surface"?e.tap:r.tap,maxPixelRatio:ne(e.maxPixelRatio,.5,4,r.maxPixelRatio),respectReducedMotion:typeof e.respectReducedMotion=="boolean"?e.respectReducedMotion:r.respectReducedMotion};var d}function la(e,r,t,o,a,s={x:.5,y:.5}){if(!(e>0&&r>0&&t>0&&o>0))return{scale:[1,1],offset:[0,0]};let u=e/r,l=t/o,f=l>u,p=a==="cover"?f?[u/l,1]:[1,l/u]:f?[1,l/u]:[u/l,1];return{scale:p,offset:a==="cover"?[(1-p[0])*s.x,(1-p[1])*s.y]:[.5*(1-p[0]),.5*(1-p[1])]}}function Jr(e,r,t,o){let a=Math.max(2,Math.round(e*t)),s=Math.max(2,Math.round(a*r)),u=Math.min(16,Math.max(1,o)),l=Math.ceil(o/u);return{width:s,height:a,columns:u,rows:l,atlasWidth:u*s,atlasHeight:l*a}}function hr(e){let r=e.replace("#",""),t=r.length===3?r.split("").map(a=>a+a).join(""):r,o=Number.parseInt(t,16);return Number.isFinite(o)&&t.length===6?[(o>>16&255)/255,(o>>8&255)/255,(255&o)/255]:[0,0,0]}function Ci(e){let r=new Uint32Array(256),t=0;for(let u=0;u+3<e.length;u+=4)e[u+3]<8||(r[Math.round(.2126*e[u]+.7152*e[u+1]+.0722*e[u+2])]++,t++);if(!t)return[0,1];let o=u=>{let l=0;for(let f=0;f<256;f++)if(l+=r[f],l>=t*u)return f/255;return 1},a=o(.02),s=o(.98);return s-a<.08?[0,1]:[a,s]}var Xn=e=>e.hover!=="fluid"||e.fluid?e.hover:"none";function Li(e,r,t=24,o=.12,a="ellipse"){return e.width>0&&e.height>0&&{x:(r.left-t-e.left)/e.width,y:(r.top-t-e.top)/e.height,width:(r.width+2*t)/e.width,height:(r.height+2*t)/e.height,feather:o,shape:a}}var an,Pi=/\.(mp4|webm|mov|m4v|ogv)(\?|#|$)/i,sa=/swiftshader|llvmpipe|softpipe|software|basic render/i;function _i(){if(an)return an;if(typeof document>"u"||globalThis.WebGL2RenderingContext===void 0)return an="none";try{let e=ro();if(e)return an=sa.test(e.renderer)?"software":"gpu";let r=document.createElement("canvas").getContext("webgl2");if(!r)return an="none";let t=r.getExtension("WEBGL_debug_renderer_info"),o=String(r.getParameter(t?t.UNMASKED_RENDERER_WEBGL:r.RENDERER)??"");return r.getExtension("WEBGL_lose_context")?.loseContext(),an=sa.test(o)?"software":"gpu"}catch{return an="none"}}var oo=(e,r)=>`${e.fontWeight} ${Math.max(1,r.height*e.glyphScale)}px ${e.font}`,Ea=(e,r)=>`${Dt(e.charset).join("")}\0${oo(e,r)}\0${r.width}x${r.height}x${r.columns}`;function ka(e,r,t,o){let a=Math.min(globalThis.devicePixelRatio||1,e.maxPixelRatio,Math.sqrt(8294400/Math.max(1,r*t)));return o<1&&a>1?Math.max(1,a*o):a}function Ta(e,r,t){let o=Dt(e.charset),a=document.createElement("canvas");a.width=r.atlasWidth,a.height=r.atlasHeight;let s=a.getContext("2d");s.fillStyle="#fff",s.textAlign="center",s.textBaseline="alphabetic";let u=oo(e,r),l=Math.max(1,r.height*e.glyphScale),f=`${e.fontWeight} ${l}px "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic", YuGothic, "Noto Sans JP", "Noto Sans CJK JP", Meiryo, sans-serif, ${e.font}`;s.font=u;let p=s.measureText("M"),d=p.actualBoundingBoxAscent||r.height*e.glyphScale*.7,x=p.actualBoundingBoxDescent||0,v=(r.height+d-x)/2;o.forEach((b,W)=>{let L=W%r.columns*r.width+r.width/2,z=Math.floor(W/r.columns)*r.height+v,oe=wa(b);if(s.save(),s.beginPath(),s.rect(L-r.width/2,z-v,r.width,r.height),s.clip(),oe){s.font=f;let M=s.measureText(b),_=Math.max(M.width,(M.actualBoundingBoxLeft||0)+(M.actualBoundingBoxRight||0)),$=(M.actualBoundingBoxAscent||.88*l)+(M.actualBoundingBoxDescent||.12*l),se=Math.min(1,.94*r.width/Math.max(1,_),.94*r.height/Math.max(1,$));s.translate(L,Math.floor(W/r.columns)*r.height+r.height/2),s.scale(se,se),s.translate(((M.actualBoundingBoxLeft||0)-(M.actualBoundingBoxRight||0))/2,((M.actualBoundingBoxAscent||.88*l)-(M.actualBoundingBoxDescent||.12*l))/2),s.fillText(b,0,0),s.font=u}else{let M=s.measureText(b).width;s.translate(L,z),M>.96*r.width&&s.scale(.96*r.width/M,1),s.fillText(b,0,0)}s.restore()});let w=!0,n=document.fonts;try{w=!n?.check||n.check(u,o.join(""))}catch{}return t&&queueMicrotask(()=>{a.width=a.height=1}),{image:a,final:w}}var ca=()=>{};function Ra(e,r={}){if(typeof document>"u"||e.ownerDocument!==document)return!1;let t=e.clientWidth,o=e.clientHeight;if(!t||!o)return!1;let a=ro();if(!a||a.lost)return!1;let{clear:s,source:u,interactionTarget:l,onError:f,label:p,...d}=r,x=Qr(d),v=Jr(x.cellSize,x.cellAspect,ka(x,t,o,a.scale),Dt(x.charset).length),w=Ea(x,v);if(a.hasAtlas(w))return!1;try{a.releaseAtlas(a.atlas(w,()=>Ta(x,v,!0),ca),ca)}catch{return!1}return!0}function gr(e={}){let r=_i();return r==="gpu"||r==="software"&&!!e.allowSoftware}function Aa(e,r={}){let t=i=>typeof HTMLElement<"u"&&i instanceof HTMLElement,o=i=>{let m=i.clear;return a(m)?{element:null,rest:{...i,clear:!1}}:t(m)?{element:{element:m},rest:{...i,clear:void 0}}:m&&typeof m=="object"&&t(m.element)?{element:m,rest:{...i,clear:void 0}}:{element:null,rest:i}},a=i=>!!i&&typeof i=="object"&&"rects"in i,s=o(r).element,u=a(r.clear)?r.clear:null,l=Qr(o(r).rest),f=r.onError,p=e.ownerDocument,d=p&&typeof document<"u"&&p!==document?null:ro(),x=d?e.getContext("2d",{alpha:!0}):null,v=!(!d||!x),w=v?d.gl:e.getContext("webgl2",{alpha:!0,antialias:!1,depth:!1,stencil:!1,premultipliedAlpha:!0,powerPreference:"high-performance"});if(!w)throw new Error("WebGL2 is not available for the glyph field.");let n=w;v&&(i=>{ya.add(i)})(e),e.setAttribute("role","img"),e.setAttribute("aria-label",r.label??"ASCII artwork"),e.dataset.renderer="glyph-field";let b=!1,W=v?null:n.getExtension("KHR_parallel_shader_compile"),L,z,oe=null,M=null,_=null,$=null,se=null,Fe=[],Me=[],G=null,me=!1,ye=null,A=null,D=[],B=0,Z=0,ae=1,Be=0,ge=Jr(l.cellSize,l.cellAspect,1,2),Ge=2,Ne=0,Re=0,Xe=0,V=null,Ze=!1,it=null,ht=0,ft=0,et=0,lt=null,tt=0,Ln=0,un=0,hn=!0,_e=0,dt=[0,1],Pn=-1/0,De=-1/0,Wt=!1,kt=(()=>{let i=typeof navigator>"u"?void 0:navigator;return 1e3/(i&&(i.hardwareConcurrency>0&&i.hardwareConcurrency<=2||i.deviceMemory&&i.deviceMemory<=2||i.connection?.saveData)?30:60)-2})(),qe=new Float32Array(16),Ye=!1,Vt=0,jt=0,we=!0,st=!1,mt=!1,fn=!1,Yt=!1,Tt=!0,$e=null,yt=null,_n=1/60,Bt=0,pt=0,nt=[],rt=new Float32Array(16),dn=()=>{if(!s)return;let{element:i,padding:m=32,feather:g=.16,shape:h="rect"}=s,k=Li(e.getBoundingClientRect(),i.getBoundingClientRect(),m,g,h),T=l.clear;JSON.stringify(T)!==JSON.stringify(k)&&(l={...l,clear:k},we=!0)},c=null,C=new Uint8Array(0),E=0,ve=0,ce=!1,pe=null,Ce=new Float64Array(0),Te=!0,I=()=>{if(!u)return void(ce&&(ce=!1,we=!0));let i=u.rects,m=typeof i=="function"?i():i;if(m===pe&&!Te)return;pe=m;let g=e.getBoundingClientRect(),[h,k]=(function(y,S,P=256){let j=Math.min(.16666666666666666,P/Math.max(1,y,S));return[Math.max(2,Math.round(y*j)),Math.max(2,Math.round(S*j))]})(g.width,g.height),T=new Float64Array(4*m.length+6);T[0]=g.left,T[1]=g.top,T[2]=g.width,T[3]=g.height,T[4]=u.padding??8,T[5]=u.softness??28,m.forEach((y,S)=>{T[6+4*S]=y.left,T[7+4*S]=y.top,T[8+4*S]=y.width,T[9+4*S]=y.height});let O=!Te&&T.length===Ce.length&&T.every((y,S)=>y===Ce[S]);Te=!1,O&&ce||(Ce=T,C=(function(y,S,P,j,R=8,X=28,re=new Uint8Array(P*j)){let Y=P*j;if(re.length!==Y&&(re=new Uint8Array(Y)),re.fill(0),!(S.width>0&&S.height>0&&y.length))return re;let J=P/S.width,K=j/S.height,le=Math.max(0,Math.round(X/2.56*J)),U=R+.5*X;for(let te of y){if(!(te.width>0&&te.height>0))continue;let Pe=Math.max(0,Math.round((te.left-U-S.left)*J)),Oe=Math.min(P,Math.round((te.left+te.width+U-S.left)*J)),Se=Math.max(0,Math.round((te.top-U-S.top)*K)),ke=Math.min(j,Math.round((te.top+te.height+U-S.top)*K));for(let ze=Se;ze<ke;ze++)re.fill(255,(j-1-ze)*P+Pe,(j-1-ze)*P+Math.max(Pe,Oe))}if(!le)return re;let fe=new Float32Array(Math.max(P,j)),F=new Float32Array(Math.max(P,j)+1),Ee=(te,Pe,Oe)=>{for(let Se=0;Se<3;Se++){for(let ke=0;ke<te;ke++)fe[ke]=re[Oe+ke*Pe];F[0]=0;for(let ke=0;ke<te;ke++)F[ke+1]=F[ke]+fe[ke];for(let ke=0;ke<te;ke++){let ze=Math.max(0,ke-le),gt=Math.min(te,ke+le+1);re[Oe+ke*Pe]=Math.round((F[gt]-F[ze])/(gt-ze))}}};for(let te=0;te<j;te++)Ee(P,1,te*P);for(let te=0;te<P;te++)Ee(j,P,te);return re})(m,g,h,k,T[4],T[5],C),mt||(c??(c=ut(n.LINEAR)),n.bindTexture(n.TEXTURE_2D,c),n.pixelStorei(n.UNPACK_ALIGNMENT,1),n.pixelStorei(n.UNPACK_FLIP_Y_WEBGL,!1),n.pixelStorei(n.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!1),h!==E||k!==ve?n.texImage2D(n.TEXTURE_2D,0,n.R8,h,k,0,n.RED,n.UNSIGNED_BYTE,C):n.texSubImage2D(n.TEXTURE_2D,0,0,0,h,k,n.RED,n.UNSIGNED_BYTE,C),n.pixelStorei(n.UNPACK_ALIGNMENT,4),E=h,ve=k,ce=!0,we=!0))},H=()=>{we=!0,Ae()},Q=!1,ue=()=>{let i=!!u&&typeof u.rects=="function"&&typeof window<"u"&&typeof window.addEventListener=="function";i!==Q&&(Q=i,i?window.addEventListener("scroll",H,{passive:!0,capture:!0}):window.removeEventListener("scroll",H,{capture:!0}))},he=i=>i==="lantern"||i==="loupe"||i==="reveal",ie={target:null,at:null,strength:0,trail:[]},Ie=new Float32Array(36),be=null,Le=null,Ke=!1,ct=()=>{if(!B||!Z)return null;let i=B/Z,m=Math.round(i>=1?128:128*i),g=Math.round(i>=1?128/i:128);return be&&be.width===m&&be.height===g||(be=new xi(m,g),Le||(Le=ut(n.LINEAR)),n.bindTexture(n.TEXTURE_2D,Le),n.texImage2D(n.TEXTURE_2D,0,n.RGBA8,m,g,0,n.RGBA,n.UNSIGNED_BYTE,be.pixels),Ke=!0),be},de=null,Ve=null,Dn=new Uint8Array(0),Mt=!1,$t=null,Rt=null,In=-1,Kt=[-.5,-.8],At=[0,0],Qt=()=>{if(de&&V)try{if(Rt??(Rt=document.createElement("canvas").getContext("2d",{willReadFrequently:!0})),!Rt)return;let i=V instanceof HTMLVideoElement,m=i?de.cols>>1:de.cols,g=i?de.rows>>1:de.rows,h=Rt.canvas;h.width!==m||h.height!==g?(h.width=m,h.height=g):Rt.clearRect(0,0,m,g);let k=ht||1,T=ft||1;Rt.drawImage(V,wt.offset[0]*k,wt.offset[1]*T,wt.scale[0]*k,wt.scale[1]*T,0,0,m,g),$t=(function(O,y,S,P,j=O){let R=y*S,X=P?.length===R*Hn?P:new Float32Array(R*Hn);if(!R)return X;let re=Math.min(y,S),Y=new Float32Array(R),J=new Float32Array(R),K=new Float32Array(R),le=new Float32Array(R),U=new Float32Array(R),fe=new Float32Array(R);for(let ee=0;ee<R;ee++){let xe=O[4*ee+3]/255;Y[ee]=(.299*O[4*ee]+.587*O[4*ee+1]+.114*O[4*ee+2])/255*xe}J.set(Y),Ue(J,fe,y,S,Math.max(1,Math.round(.012*re))),K.set(Y),Ue(K,fe,y,S,Math.max(1,Math.round(.03*re)));for(let ee=0;ee<R;ee++){le[ee]=Math.abs(Y[ee]-J[ee]);let xe=Math.max(0,Y[ee]-.55)/.45;U[ee]=xe*xe}Ue(le,fe,y,S,Math.max(1,Math.round(.02*re)));let F=1/Math.max(.02,xt(le,.95));Ue(U,fe,y,S,Math.max(1,Math.round(.05*re)));let Ee=1/Math.max(.03,xt(U,.98)),te=Math.max(1,Math.ceil(Math.sqrt(R/12e3))),Pe=Math.max(1,Math.floor(y/te)),Oe=Math.max(1,Math.floor(S/te)),Se=Pe*Oe,ke=O,ze=j;if(te>1){let ee=new Uint8ClampedArray(4*Se),xe=j===O?ee:new Uint8ClampedArray(4*Se);for(let Je=0;Je<Oe;Je++)for(let He=0;He<Pe;He++){let vt=[0,0,0,0,0,0,0];for(let ot=Je*te;ot<(Je+1)*te;ot++)for(let Hr=He*te;Hr<(He+1)*te;Hr++){let Qo=4*(ot*y+Hr);for(let Lt=0;Lt<4;Lt++)vt[Lt]+=O[Qo+Lt];if(xe!==ee)for(let Lt=0;Lt<3;Lt++)vt[4+Lt]+=j[Qo+Lt]}let Et=4*(Je*Pe+He),Ko=te*te;for(let ot=0;ot<4;ot++)ee[Et+ot]=vt[ot]/Ko;if(xe!==ee){for(let ot=0;ot<3;ot++)xe[Et+ot]=vt[4+ot]/Ko;xe[Et+3]=ee[Et+3]}}ke=ee,ze=xe}lr?.n!==Se&&(lr=new yi(Se)),lr.reset();let{depth:gt,water:bt,sky:rn,falls:on}=Mi(ke,ze,Pe,Oe,lr),xn=xt(gt,.03),yn=xt(gt,.97),zr=Math.max(.05,yn-xn),Mn=0,wn=0,Ct=0,nr=new Float32Array(R);for(let ee=0;ee<S;ee++)for(let xe=0;xe<y;xe++){let Je=ee*y+xe,He=Je*Hn,vt=at((cr(gt,Pe,Oe,xe,ee,y,S)-xn)/zr);X[He+1]=vt,X[He+8]=at(cr(bt,Pe,Oe,xe,ee,y,S)),X[He+9]=at(cr(rn,Pe,Oe,xe,ee,y,S)),X[He+10]=at(cr(on,Pe,Oe,xe,ee,y,S));let Et=vt*vt*vt*(.25+Y[Je]);Mn+=(xe+.5)/y*Et,wn+=(ee+.5)/S*Et,Ct+=Et,nr[Je]=Math.hypot(K[ee*y+Math.min(y-1,xe+1)]-K[ee*y+Math.max(0,xe-1)],K[Math.min(S-1,ee+1)*y+xe]-K[Math.max(0,ee-1)*y+xe])}Mn=Ct>0?Math.max(.3,Math.min(.7,Mn/Ct)):.5,wn=Ct>0?Math.max(.3,Math.min(.7,wn/Ct)):.5;let Nn=1/Math.max(.004,xt(nr,.97));for(let ee=0;ee<S;ee++)for(let xe=0;xe<y;xe++){let Je=ee*y+xe,He=Je*Hn,vt=(K[ee*y+Math.min(y-1,xe+1)]-K[ee*y+Math.max(0,xe-1)])*Nn,Et=(K[Math.min(S-1,ee+1)*y+xe]-K[Math.max(0,ee-1)*y+xe])*Nn;X[He]=K[Je],X[He+2]=Math.min(1,U[Je]*Ee),X[He+3]=Math.min(1,le[Je]*F),X[He+4]=Math.max(-1,Math.min(1,-vt)),X[He+5]=Math.max(-1,Math.min(1,-Et)),X[He+6]=Mn,X[He+7]=wn}return X})(Rt.getImageData(0,0,m,g).data,m,g,$t),At[0]=m,At[1]=g,(function(O,y,S=[-.5,-.8],P=O.cols,j=O.rows){let{cols:R,rows:X,speed:re,damp:Y,wall:J}=O,K=Hn;if(y.length!==P*j*K)return S;let le=0,U=0,fe=0;for(let F=0,Ee=0;F<X;F++){let te=Math.min(j-1,F*j/X|0);for(let Pe=0;Pe<R;Pe++,Ee++){let Oe=Math.min(P-1,Pe*P/R|0),Se=(te*P+Oe)*K,ke=y[Se+3],ze=y[Se+8],gt=y[Se+9],bt=y[Se+2],rn=y[Se+1],on=Oe<P-1?K:0,xn=Oe>0?-K:0,yn=te<j-1?P*K:0,zr=te>0?-P*K:0,Mn=Math.hypot(y[Se+1+on]-y[Se+1+xn],y[Se+1+yn]-y[Se+1+zr]),wn=Math.hypot(y[Se+4],y[Se+5]),Ct=Math.max(ze,.9*gt),nr=1-En(.2,.8,ke),Nn=Math.max(.12,Math.max(Ct,.2+.65*nr)*(1-.45*En(.55,.95,rn)*(1-ze)));re[Ee]=Nn*Nn;let ee=Math.max(0,1-Ct);Y[Ee]=.9*ze+1.6*gt*(1-ze)+ee*(1.4+6.5*En(.25,.9,ke)),J[Ee]=Math.min(.4,.35*En(.12,.35,Mn)*(1-.6*ze)+.1*En(.6,1,wn)*(1-Ct)),le+=(Pe/(R-1)-.5)*bt,U+=(F/(X-1)-.5)*bt,fe+=bt}}if(aa(re,R,X,2),aa(Y,R,X,1),fe>.5){let F=Math.hypot(le,U);F/fe>.02&&(S[0]=le/F,S[1]=U/F)}})(de,$t,Kt,m,g)}catch{}},mn=(i,m,g)=>{if(!B||!Z)return;let h=B/Z,k=Math.round(h>=1?128:128*h),T=Math.round(h>=1?128/h:128);de&&de.cols===k&&de.rows===T||(de=new wi(k,T),$t=null,Dn=new Uint8Array(k*T*4),Ve??(Ve=ut(n.LINEAR)),n.bindTexture(n.TEXTURE_2D,Ve),n.texImage2D(n.TEXTURE_2D,0,n.RGBA8,k,T,0,n.RGBA,n.UNSIGNED_BYTE,null)),de.base=1.1*Math.min(k,T),de.mass=0,de.calm=7,de.fade=1.6,Qt(),In=un,de.drop(i*(k-1),m*(T-1),g,2.2),Ae()},q=i=>{if(!de?.live||!Ve)return!!Mt&&(Mt=!1,!0);V instanceof HTMLVideoElement&&In!==un&&(Qt(),In=un),de.step(i,.45+.55*Math.exp(-de.age/.7));let m=Math.min(1,Math.exp(-(de.age-.9)/.5));return m<.02?(de.clear(),Mt=!1,!0):((function(g,h,k,T,O=1,y=g.cols,S=g.rows){let{cols:P,rows:j,h:R,trace:X}=g,re=O/Math.max(.01,g.front),Y=k[0],J=k[1],K=h.length===y*S*11;for(let le=0,U=0;le<j;le++){let fe=Math.min(S-1,le*S/j|0);for(let F=0;F<P;F++,U++){let Ee=R[U]*re,te=11*(fe*y+Math.min(y-1,F*y/P|0)),Pe=K?h[te+9]:0,Oe=K?Math.max(h[te+8],.75*(1-En(.1,.45,h[te+3]))*(1-Pe)):0,Se=Math.max(0,1-Math.max(Oe,Pe)),ke=.5*(R[F<P-1?U+1:U]-R[F>0?U-1:U])*re,ze=.5*(R[le<j-1?U+P:U]-R[le>0?U-P:U])*re,gt=(6*-ke+(K?.35*h[te+4]:0))*Y+(6*-ze+(K?.35*h[te+5]:0))*J,bt=Math.max(-1,Math.min(1,gt)),rn=Ee>0?Ee:.45*Ee,on=Oe*(.8*rn+.4*bt*Math.min(1,4*Math.abs(Ee)))+Pe*(.3*Math.min(1,X[U]*re)+.15*rn)+Se*(.55*rn+.25*bt*Math.min(1,4*Math.abs(Ee))),xn=Oe*Math.max(0,bt)**3*Math.min(1,3*Math.max(0,Ee))*.9+Se*Math.max(0,bt)**4*Math.min(1,3*Math.max(0,Ee))*.25;on=Math.max(-1,Math.min(1,on));let yn=Math.round(32767*on+32768);T[4*U]=yn>>>8,T[4*U+1]=255&yn,T[4*U+2]=Math.round(255*Math.min(1,xn)),T[4*U+3]=255}}})(de,$t??new Float32Array(0),Kt,Dn,m,At[0],At[1]),n.bindTexture(n.TEXTURE_2D,Ve),n.pixelStorei(n.UNPACK_FLIP_Y_WEBGL,!1),n.pixelStorei(n.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!1),n.texSubImage2D(n.TEXTURE_2D,0,0,0,de.cols,de.rows,n.RGBA,n.UNSIGNED_BYTE,Dn),Mt=!0,!0)},St=0,Ot=typeof matchMedia=="function"?matchMedia("(prefers-reduced-motion: reduce)"):null,We=()=>l.respectReducedMotion&&!!Ot?.matches,Gt,Nt=new Promise(i=>{Gt=i}),Qe=!0,Ft=i=>f?.(i instanceof Error?i:new Error(String(i))),qt=(i,m)=>{let g=n.createShader(i);return D.push(g),n.shaderSource(g,m),n.compileShader(g),g},zt=i=>{if(v)return d.program(i);A??(A=qt(n.VERTEX_SHADER,`#version 300 es
void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.-1.,0.,1.);}`));let m=n.createProgram(),g=qt(n.FRAGMENT_SHADER,i);return n.attachShader(m,A),n.attachShader(m,g),n.linkProgram(m),{program:m,locations:null,fragment:g}},Jt=(i,m=!1)=>{if(i.locations)return!0;if(v)return d.linked(i,m);let{program:g,fragment:h}=i;if(!m&&W&&!n.getProgramParameter(g,W.COMPLETION_STATUS_KHR))return!1;if(!n.getProgramParameter(g,n.LINK_STATUS)){if(n.isContextLost())return!1;throw new Error(n.getShaderInfoLog(h)||n.getProgramInfoLog(g)||"Glyph field program failed to link.")}let k={};for(let T=n.getProgramParameter(g,n.ACTIVE_UNIFORMS)-1;T>=0;T--){let O=n.getActiveUniform(g,T).name.replace(/\[0\]$/,"");k[O]=n.getUniformLocation(g,O)}return i.locations=k,!0},Zt=(i=!1)=>!!oe&&!!M&&Jt(oe,i)&&Jt(M,i),ut=i=>{let m=n.createTexture();return n.bindTexture(n.TEXTURE_2D,m),n.texParameteri(n.TEXTURE_2D,n.TEXTURE_MIN_FILTER,i),n.texParameteri(n.TEXTURE_2D,n.TEXTURE_MAG_FILTER,i===n.LINEAR_MIPMAP_LINEAR?n.LINEAR:i),n.texParameteri(n.TEXTURE_2D,n.TEXTURE_WRAP_S,n.CLAMP_TO_EDGE),n.texParameteri(n.TEXTURE_2D,n.TEXTURE_WRAP_T,n.CLAMP_TO_EDGE),m},Un=()=>{se&&(n.deleteTexture(se.ink),n.deleteTexture(se.under),n.deleteFramebuffer(se.buffer),se=null)},Bn=()=>(function(i,m,g,h,k,T,O){if(i!=="fill"||!(k>0&&T>0))return[O.width,O.height];let y=m*h,S=y*g;return[k/Math.max(1,Math.floor(k/S+1e-6)),T/Math.max(1,Math.floor(T/y+1e-6))]})(l.cellFit,l.cellSize,l.cellAspect,ae,B,Z,ge),On=()=>!!l.fluid&&Xn(l)==="fluid",pn=()=>{G?.release(),me=!1,Fe.forEach(i=>n.deleteTexture(i)),Me.forEach(i=>n.deleteFramebuffer(i)),Fe=[],Me=[]};function gn(){_&&!v&&n.deleteProgram(_.program),_=zt((i=>`#version 300 es
precision highp float;
precision highp sampler2D;
uniform sampler2D uPrevious;
uniform vec2 uSize;
uniform float uAspect, uDt, uDecay, uEnergyDecay, uRadius, uSplat;
uniform vec2 uFrom, uTo, uForce;
out vec4 outColor;
${ua(i)}
float segment(vec2 p,vec2 a,vec2 b){vec2 pa=p-a,ba=b-a;float h=clamp(dot(pa,ba)/max(dot(ba,ba),1e-8),0.,1.);return length(pa-ba*h);}
void main(){
  vec2 uv=gl_FragCoord.xy/uSize;
  vec4 here=decodeFluid(texture(uPrevious,uv));
  vec4 state=decodeFluid(texture(uPrevious,uv-uDt*here.xy*vec2(1./uAspect,1.)));
  state.xy*=exp(-uDt*uDecay);
  state.z*=exp(-uDt*uEnergyDecay);
  if(uSplat>.5){
    vec2 scale=vec2(uAspect,1.);
    float d=segment(uv*scale,uFrom*scale,uTo*scale);
    float g=exp(-d*d/(uRadius*uRadius));
    state.xy+=uForce*g;
    state.z=min(1.,state.z+g*min(1.,length(uForce)*.5+.08));
  }
  float speed=length(state.xy);
  if(speed>5.)state.xy*=5./speed;
  outColor=encodeFluid(state);
}`)(b)),v?G?.release():G?.dispose(),G=b?null:(function(i,m,g){let h={splat:m(Ja),curl:m(Za),vorticity:m(ei),divergence:m(ti),fade:m(ni),pressure:m(ri),gradient:m(oi),advect:m(ai)},k=Object.values(h),T=0,O=0,y=[],S=[],P=null,j=null,R=U=>{let fe=i.createTexture();i.bindTexture(i.TEXTURE_2D,fe),i.texParameteri(i.TEXTURE_2D,i.TEXTURE_MIN_FILTER,U),i.texParameteri(i.TEXTURE_2D,i.TEXTURE_MAG_FILTER,U),i.texParameteri(i.TEXTURE_2D,i.TEXTURE_WRAP_S,i.CLAMP_TO_EDGE),i.texParameteri(i.TEXTURE_2D,i.TEXTURE_WRAP_T,i.CLAMP_TO_EDGE),i.texImage2D(i.TEXTURE_2D,0,i.RGBA16F,T,O,0,i.RGBA,i.HALF_FLOAT,null);let F=i.createFramebuffer();return i.bindFramebuffer(i.FRAMEBUFFER,F),i.framebufferTexture2D(i.FRAMEBUFFER,i.COLOR_ATTACHMENT0,i.TEXTURE_2D,fe,0),i.checkFramebufferStatus(i.FRAMEBUFFER)!==i.FRAMEBUFFER_COMPLETE?(i.deleteFramebuffer(F),i.deleteTexture(fe),null):(i.viewport(0,0,T,O),i.clearColor(0,0,0,1),i.clear(i.COLOR_BUFFER_BIT),{texture:fe,buffer:F})},X=U=>{U&&(i.deleteTexture(U.texture),i.deleteFramebuffer(U.buffer))},re=()=>{[...y,...S,P,j].forEach(X),y=[],S=[],P=j=null},Y=(U,fe)=>{let F=U.locations;return i.useProgram(U.program),i.bindFramebuffer(i.FRAMEBUFFER,fe.buffer),i.uniform2f(F.uTexel,1/T,1/O),F},J=(U,fe,F,Ee)=>{i.activeTexture(i.TEXTURE0+F),i.bindTexture(i.TEXTURE_2D,Ee),i.uniform1i(U[fe],F)},K=()=>i.drawArrays(i.TRIANGLES,0,3),le=U=>{let fe=U[0];U[0]=U[1],U[1]=fe};return{resize(U,fe){re(),T=U,O=fe;let F=[R(i.LINEAR),R(i.LINEAR),R(i.NEAREST),R(i.NEAREST),R(i.NEAREST),R(i.NEAREST)];return i.bindFramebuffer(i.FRAMEBUFFER,null),F.some(Ee=>!Ee)?(F.forEach(X),!1):(y=[F[0],F[1]],S=[F[2],F[3]],P=F[4],j=F[5],!0)},ready:()=>k.every(g),step(U,fe){if(!y.length||!P||!j)return;let F;i.viewport(0,0,T,O),U&&(F=Y(h.splat,y[1]),J(F,"uVelocity",0,y[0].texture),i.uniform2f(F.uFrom,U.from[0],U.from[1]),i.uniform2f(F.uTo,U.to[0],U.to[1]),i.uniform2f(F.uForce,U.force[0],U.force[1]),i.uniform1f(F.uAspect,fe.aspect),i.uniform1f(F.uRadius,fe.radius),K(),le(y)),fe.curl>0&&(F=Y(h.curl,j),J(F,"uVelocity",0,y[0].texture),K(),F=Y(h.vorticity,y[1]),J(F,"uVelocity",0,y[0].texture),J(F,"uCurl",1,j.texture),i.uniform1f(F.uStrength,fe.curl),i.uniform1f(F.uDt,fe.dt),K(),le(y)),F=Y(h.divergence,P),J(F,"uVelocity",0,y[0].texture),K(),F=Y(h.fade,S[1]),J(F,"uSource",0,S[0].texture),i.uniform1f(F.uAmount,.8),K(),le(S);for(let Ee=0;Ee<20;Ee++)F=Y(h.pressure,S[1]),J(F,"uPressure",0,S[0].texture),J(F,"uDivergence",1,P.texture),K(),le(S);F=Y(h.gradient,y[1]),J(F,"uPressure",0,S[0].texture),J(F,"uVelocity",1,y[0].texture),K(),le(y),F=Y(h.advect,y[1]),J(F,"uVelocity",0,y[0].texture),i.uniform1f(F.uDt,fe.dt),i.uniform1f(F.uDissipation,fe.dissipation),K(),le(y),i.bindFramebuffer(i.FRAMEBUFFER,null)},get velocity(){return y[0]?.texture??null},get size(){return[T,O]},release:re,dispose(){re(),k.forEach(({program:U})=>i.deleteProgram(U))}}})(n,zt,i=>Jt(i))}let To=()=>{pn();let i=l.fluid;if(!(i&&On()&&B&&Z))return;_||gn();let m=i.resolution,g=B/Z;if(Ne=g>=1?m:Math.max(8,Math.round(m*g)),Re=g>=1?Math.max(8,Math.round(m/g)):m,me=!!G&&G.resize(Ne,Re),me)return void(Xe=0);let h=()=>{pn();for(let k=0;k<2;k++){let T=ut(n.LINEAR);n.texImage2D(n.TEXTURE_2D,0,b?n.RGBA8:n.RGBA16F,Ne,Re,0,n.RGBA,b?n.UNSIGNED_BYTE:n.HALF_FLOAT,null);let O=n.createFramebuffer();n.bindFramebuffer(n.FRAMEBUFFER,O),n.framebufferTexture2D(n.FRAMEBUFFER,n.COLOR_ATTACHMENT0,n.TEXTURE_2D,T,0),Fe.push(T),Me.push(O)}return n.checkFramebufferStatus(n.FRAMEBUFFER)===n.FRAMEBUFFER_COMPLETE};if(!h()){if(b)throw new Error("The glyph field could not allocate its fluid buffers.");b=!0,Ro(),gn(),h()}for(let k of Me)n.bindFramebuffer(n.FRAMEBUFFER,k),n.viewport(0,0,Ne,Re),n.clearColor(b?.5:0,b?.5:0,0,1),n.clear(n.COLOR_BUFFER_BIT);n.bindFramebuffer(n.FRAMEBUFFER,null),Xe=0};function Ro(){oe&&!v&&n.deleteProgram(oe.program),M&&!v&&n.deleteProgram(M.program),Un(),oe=zt(ha(b)),M=zt(fa),(v?d.canCompileInParallel:W)||Zt(!0)}let Ao=()=>oo(l,ge),Rr=()=>{we=!0,Ae()},So=()=>Ea(l,ge),Ar=()=>{if(Ge=Dt(l.charset).length,ge=Jr(l.cellSize,l.cellAspect,ae,Ge),Be=ae,v){let g=So();if($?.key!==g){let h=$;$=d.atlas(g,Sr,Rr),d.releaseAtlas(h,Rr),L=$.texture}return void(we=!0)}let{image:m}=Sr();n.bindTexture(n.TEXTURE_2D,L),n.pixelStorei(n.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!1),n.texImage2D(n.TEXTURE_2D,0,n.RGBA8,n.RGBA,n.UNSIGNED_BYTE,m),m.width=m.height=1,we=!0};function Sr(){return Ta(l,ge,v)}let Fo=typeof document>"u"?void 0:document.fonts,Fr=()=>{if(!Fo?.load)return;let i=Ao();Fo.load(i,Dt(l.charset).join("")).then(()=>{if(!st&&!mt&&Ao()===i)return v?void($&&!$.final&&$.key===So()&&d.paintAtlas($,Sr)):(Ar(),void Ae())},()=>{})},Co=i=>i.trim().replace(/^["']|["']$/g,"").toLowerCase(),Lo=()=>{if(dt=[0,1],V&&l.levels!=="none")try{let i=document.createElement("canvas");i.width=i.height=64;let m=i.getContext("2d",{willReadFrequently:!0});V===lt&&(m.imageSmoothingQuality="medium"),m.drawImage(V,0,0,64,64),dt=Ci(m.getImageData(0,0,64,64).data)}catch{dt=[0,1]}},en=null,Qn=null,Jn=!1,Cr=-1/0,Zn=new Uint8Array(0),tn=null,Po=()=>{if(Jn=!1,!V||l.scope==="all")return;let i=ht||1,m=ft||1,g=Math.max(8,Math.round(i>=m?96:96*i/m)),h=Math.max(8,Math.round(m>=i?96:96*m/i));try{if(tn??(tn=document.createElement("canvas").getContext("2d",{willReadFrequently:!0})),!tn)return;let k=tn.canvas;k.width!==g||k.height!==h?(k.width=g,k.height=h):tn.clearRect(0,0,g,h),tn.drawImage(V,0,0,g,h),Qn=ba(tn.getImageData(0,0,g,h).data,g,h,null,Qn)}catch{return}if(Qn.key!=="none"){Zn.length!==g*h*4&&(Zn=new Uint8Array(g*h*4));for(let k=0;k<g*h;k++)Zn[4*k+3]=Math.round(255*Qn.subject[k]);en??(en=ut(n.LINEAR)),n.bindTexture(n.TEXTURE_2D,en),n.pixelStorei(n.UNPACK_FLIP_Y_WEBGL,!1),n.pixelStorei(n.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!1),n.texImage2D(n.TEXTURE_2D,0,n.RGBA8,g,h,0,n.RGBA,n.UNSIGNED_BYTE,Zn),Jn=!0}},Lr=()=>{if(!V)return;let i=performance.now();V instanceof HTMLVideoElement&&!(i-Pn>1500)||(Lo(),Pn=i),V instanceof HTMLVideoElement&&!(i-Cr>160)||(Po(),Cr=i),n.bindTexture(n.TEXTURE_2D,z),n.pixelStorei(n.UNPACK_FLIP_Y_WEBGL,!1),n.pixelStorei(n.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!1);try{n.texImage2D(n.TEXTURE_2D,0,n.RGBA8,n.RGBA,n.UNSIGNED_BYTE,V),n.generateMipmap(n.TEXTURE_2D);let m=V;Ln=(m.videoWidth||m.naturalWidth||m.width)*(m.videoHeight||m.naturalHeight||m.height)*4*4/3}catch(m){Ft(m)}},_o=()=>{b=!n.getExtension("EXT_color_buffer_float")&&!n.getExtension("EXT_color_buffer_half_float"),Ro(),ye=v?d.vertexArray():n.createVertexArray(),v||(L=ut(n.NEAREST)),z=ut(n.LINEAR_MIPMAP_LINEAR),n.bindTexture(n.TEXTURE_2D,z),n.texImage2D(n.TEXTURE_2D,0,n.RGBA8,1,1,0,n.RGBA,n.UNSIGNED_BYTE,new Uint8Array([0,0,0,255])),n.generateMipmap(n.TEXTURE_2D),B=Z=0,Be=0,vn(),Fr(),V&&Lr()};function vn(){let i=e.clientWidth||e.clientHeight?{width:e.clientWidth,height:e.clientHeight}:e.getBoundingClientRect();Wt=!i.width||!i.height;let m=ka(l,i.width,i.height,v?d.scale:1),g=Math.max(1,Math.round(i.width*m)),h=Math.max(1,Math.round(i.height*m));if(g===B&&h===Z&&m===ae)return!1;let k=!B||Math.abs(g/h-B/Z)>.01;return ae=m,B=g,Z=h,e.width=B,e.height=Z,Be!==ae&&Ar(),(k||On()&&!Fe.length&&!me)&&To(),we=!0,!0}let Do=null,er=new Float32Array(18),Gn=[0,0,0],Io=[1,1,1],Uo=[0,0,0,0],wt=la(1,1,1,1,"cover"),Bo=null,Oo=0,Go=0,No=0,qo=0,zo=()=>{Do!==l&&(Do=l,Gn=hr(l.ink),Io=hr(l.highlight==="auto"?"#ffffff":l.highlight),Uo=l.background==="transparent"?[0,0,0,0]:[...hr(l.background),1],er.fill(0),l.ramp.forEach((Y,J)=>er.set(hr(Y),3*J))),Bo===l&&Oo===B&&Go===Z&&No===ht&&qo===ft||(Bo=l,Oo=B,Go=Z,No=ht,qo=ft,wt=la(B,Z,ht||1,ft||1,l.fit,l.focus)),v&&d.begin(B,Z);let i=l.fluid,m=V&&tt?ge.height/Z*tt*wt.scale[1]:1,g=(()=>{let[Y,J]=Bn(),K=Math.ceil(B/Y-1e-4),le=Math.ceil(Z/J-1e-4);if(se&&se.columns===K&&se.rows===le)return se;Un();let U=()=>{let te=ut(n.NEAREST);return n.texStorage2D(n.TEXTURE_2D,1,b?n.RGBA8:n.RGBA16F,K,le),te},fe=U(),F=U(),Ee=n.createFramebuffer();return n.bindFramebuffer(n.FRAMEBUFFER,Ee),n.framebufferTexture2D(n.FRAMEBUFFER,n.COLOR_ATTACHMENT0,n.TEXTURE_2D,fe,0),n.framebufferTexture2D(n.FRAMEBUFFER,n.COLOR_ATTACHMENT1,n.TEXTURE_2D,F,0),n.drawBuffers([n.COLOR_ATTACHMENT0,n.COLOR_ATTACHMENT1]),se={ink:fe,under:F,buffer:Ee,columns:K,rows:le}})(),h=oe.locations,k=M.locations,T=Xn(l),O=!We();n.bindFramebuffer(n.FRAMEBUFFER,g.buffer),n.viewport(0,0,g.columns,g.rows),n.useProgram(oe.program),n.activeTexture(n.TEXTURE0),n.bindTexture(n.TEXTURE_2D,z),n.uniform1i(h.uSource,0),n.activeTexture(n.TEXTURE2),n.bindTexture(n.TEXTURE_2D,(me?G?.velocity:Fe[Xe])??z),n.uniform1i(h.uFluid,2),n.activeTexture(n.TEXTURE3),n.bindTexture(n.TEXTURE_2D,Le??z),n.uniform1i(h.uTrailMap,3),n.activeTexture(n.TEXTURE6),n.bindTexture(n.TEXTURE_2D,en??z),n.uniform1i(h.uScope,6),n.activeTexture(n.TEXTURE7),n.bindTexture(n.TEXTURE_2D,Ve??z),n.uniform1i(h.uTapMap,7),n.uniform1f(h.uTapOn,Mt&&V&&Ze?1:0),n.uniform1f(h.uScopeMode,Jn&&l.scope!=="all"?l.scope==="subject"?1:2:0),n.uniform1f(h.uFluidMode,me?1:0),n.uniform1i(h.uHoverMode,T==="fluid"?1:T==="lantern"?2:T==="trail"&&Ke?3:T==="loupe"?4:T==="reveal"?5:0),n.uniform1f(h.uTrailAmount,l.trail.strength),n.uniform3f(h.uLight,ie.at?.[0]??-1,ie.at?.[1]??-1,he(T)?ie.strength:0),n.uniform3fv(h.uTrail,Ie),n.uniform1f(h.uLightRadius,l.lantern.radius),n.uniform1f(h.uLightGain,l.lantern.strength),n.uniform1f(h.uClock,performance.now()/1e3),n.uniform1f(h.uFlicker,O?1:0),n.uniform2f(h.uFluidTexel,1/Math.max(1,Ne),1/Math.max(1,Re)),n.uniform2f(h.uResolution,B,Z);let[y,S]=Bn();var P;n.uniform2f(h.uCell,y,S),n.uniform1f(h.uCount,Ge),n.uniform1f(h.uBlend,l.blend==="on"||Ge<=9&&(l.blend==="coarse"||l.blend==="auto"&&Ze)?1:0),n.uniform4f(h.uSourceMap,wt.scale[0],wt.scale[1],wt.offset[0],wt.offset[1]),n.uniform1i(h.uScene,V?0:(P=l.scene,Qa[P]??3)),n.uniform1i(h.uMark,pr.indexOf(l.mark)),n.uniform1f(h.uOrder,l.glyphOrder==="text"?1:l.glyphOrder==="scatter"&&l.mark==="glyph"?2:0);let j=l.glyphOrder==="text"&&l.textRepeat==="row"?(function(Y){let J=Dt(Y),K=[];for(let le=0;le<J.length&&K.length<16;){if(!J[le].trim()){le++;continue}let U=le;for(;le<J.length&&J[le].trim();)le++;K.push(U,le-U)}return K})(l.charset):[];qe.fill(0),qe.set(j),n.uniform2fv(h.uWords,qe),n.uniform1f(h.uWordCount,j.length/2),n.uniform1f(h.uScale,l.scale);let R=l.clear;n.uniform4f(h.uClear,R?R.x:0,R?R.y:0,R?R.width:0,R?R.height:0),n.uniform1f(h.uClearFeather,R?R.feather:.1),n.uniform1f(h.uClearShape,R&&R.shape==="rect"?1:0),n.activeTexture(n.TEXTURE8),n.bindTexture(n.TEXTURE_2D,c??z),n.uniform1i(h.uClearMap,8);let X=ce&&!!u&&!!c;n.uniform1f(h.uClearMapOn,X?Math.min(1,Math.max(0,u.strength??.85)):0),n.uniform1f(h.uClearBend,X?.035*Math.min(1,Math.max(0,u.bend??.5)):0),n.uniform2f(h.uClearTexel,1/Math.max(1,E),1/Math.max(1,ve));let re=performance.now();rt.fill(0);for(let Y=0;Y<nt.length;Y++){let J=nt[Y],K=4*Y;rt[K]=J.x,rt[K+1]=J.y,rt[K+2]=(re-J.born)/1e3,rt[K+3]=J.strength}n.uniform4fv(h.uPulse,rt),n.uniform3fv(h.uInk,Gn),n.uniform3fv(h.uRamp,er),n.uniform1f(h.uRampCount,l.color==="source"?0:l.ramp.length),n.uniform3fv(h.uHighlight,Io),n.uniform1f(h.uHighlightAuto,l.highlight==="auto"?1:0),n.uniform4fv(h.uBackground,Uo),n.uniform1f(h.uBrightness,l.brightness),n.uniform1f(h.uContrast,l.contrast),n.uniform1f(h.uGamma,l.gamma),n.uniform1f(h.uInvert,l.invert?1:0),n.uniform1f(h.uVignette,l.vignette),n.uniform1f(h.uSourceColor,l.color==="source"?1:0),n.uniform1f(h.uRefraction,i?i.refraction*(O?1:.25):0),n.uniform1f(h.uGlow,i?i.glow:0),n.uniform1f(h.uTime,jt),n.uniform1f(h.uDrift,O?l.drift:0),n.uniform1f(h.uFluidOn,i&&T==="fluid"&&(Fe.length||me)?1:0),n.uniform1f(h.uLod,l.sample==="point"?0:Math.max(0,Math.log2(Math.max(1,m))-.5)),n.uniform1f(h.uSaturation,l.saturation),n.uniform1f(h.uShade,l.shade),n.uniform1f(h.uBackdrop,V?l.backdrop:0),n.uniform2f(h.uLevels,V&&l.levels==="auto"?dt[0]:0,V&&l.levels==="auto"?dt[1]:1),n.bindVertexArray(ye),n.drawArrays(n.TRIANGLES,0,3),n.bindFramebuffer(n.FRAMEBUFFER,null),n.viewport(0,0,B,Z),n.useProgram(M.program),n.activeTexture(n.TEXTURE1),n.bindTexture(n.TEXTURE_2D,L),n.uniform1i(k.uAtlas,1),n.activeTexture(n.TEXTURE4),n.bindTexture(n.TEXTURE_2D,g.ink),n.uniform1i(k.uCells,4),n.activeTexture(n.TEXTURE5),n.bindTexture(n.TEXTURE_2D,g.under),n.uniform1i(k.uUnder,5),n.uniform2f(k.uResolution,B,Z),n.uniform2f(k.uCell,ge.width,ge.height),n.uniform2f(k.uPitch,y,S),n.uniform1f(k.uColumns,ge.columns),n.uniform1f(k.uDotScale,l.dotScale),n.uniform2f(k.uDir,Math.cos(l.markAngle*Math.PI/180),Math.sin(l.markAngle*Math.PI/180)),n.uniform1i(k.uMark,pr.indexOf(l.mark)),n.uniform4f(k.uLine,l.linePitch,l.lineWeight,l.sparkle,0),n.uniform4f(k.uInlay,l.accents,l.shuffle,Math.floor(7*jt),Dt(l.charset).length),n.uniform1f(k.uSourceColor,l.color==="source"?1:0),n.uniform3fv(k.uRamp,er),n.uniform1f(k.uRampCount,l.color==="source"?0:l.ramp.length),n.uniform4f(k.uFade,Gn[0],Gn[1],Gn[2],l.mark==="inlay"||l.glyphOrder!=="tone"&&l.mark==="glyph"?1:0),n.drawArrays(n.TRIANGLES,0,3),v&&d.present(x,B,Z)},Ho=()=>!st&&!mt&&!fn&&!Wt&&(Tt||Qe)&&!(typeof document<"u"&&document.hidden),tr=i=>{if(Ye=!1,!Ho())return;let m=(i-Vt)/1e3,g=Math.min(1/30,Math.max(1/480,m));Vt=i,_n=.9*_n+.1*Math.min(m,.25),Bt=_n>1/24?Bt+1:0;try{v&&d.overloaded&&pt<2&&Bt>10&&(pt=2),Bt>45&&pt<2&&(!v||d.atMinimum)&&(Bt=0,pt++,pt===1&&ae>1?(l={...l,maxPixelRatio:1},vn()):pt=2);let h=Zt(),k=!(Yt||pt>=2&&!(V instanceof HTMLVideoElement)||(!(V instanceof HTMLVideoElement)||V.paused||V.ended)&&(We()||!(!V&&l.scene!=="none"||l.drift>0)));k&&(jt+=g*l.speed),V instanceof HTMLVideoElement&&V.readyState>=2&&hn&&(hn=!("requestVideoFrameCallback"in V),Lr(),un++,we=!0);let T=Xn(l),O=T==="fluid"&&(yt!==null||i<St);if(O?((y,S)=>{let P=l.fluid;if(!P||!Me.length&&!me||(me?!G?.ready():!_||!Jt(_)))return;let j=B/Z,R=yt;if(yt=null,me&&G){let J=5200*P.force*(We()?.35:1);return R&&(St=S+1e3*Math.min(9,6/Math.max(.3,P.dissipation))),void G.step(R?{from:R.from,to:R.to,force:[(R.to[0]-R.from[0])*J,(R.to[1]-R.from[1])*J]}:null,{dt:Math.min(y,1/60),radius:1.1*P.radius,curl:P.curl,dissipation:P.dissipation,aspect:j})}let X=0,re=0;if(R){let J=(We()?1:3)*P.force;X=(R.to[0]-R.from[0])*j*J*4,re=(R.to[1]-R.from[1])*J*4,St=S+7/Math.min(P.dissipation,1.1*P.dissipation)*1e3}let Y=_.locations;n.bindFramebuffer(n.FRAMEBUFFER,Me[1-Xe]),n.viewport(0,0,Ne,Re),n.useProgram(_.program),n.activeTexture(n.TEXTURE0),n.bindTexture(n.TEXTURE_2D,Fe[Xe]),n.uniform1i(Y.uPrevious,0),n.uniform2f(Y.uSize,Ne,Re),n.uniform1f(Y.uAspect,j),n.uniform1f(Y.uDt,y),n.uniform1f(Y.uDecay,P.dissipation),n.uniform1f(Y.uEnergyDecay,1.1*P.dissipation),n.uniform1f(Y.uRadius,P.radius),n.uniform1f(Y.uSplat,R?1:0),n.uniform2f(Y.uFrom,R?.from[0]??0,R?.from[1]??0),n.uniform2f(Y.uTo,R?.to[0]??0,R?.to[1]??0),n.uniform2f(Y.uForce,X,re),n.drawArrays(n.TRIANGLES,0,3),Xe=1-Xe})(g,i):yt=null,he(T)&&(O=((y,S)=>{let P=l.lantern,j=ie.target;if(j){let X=ie.at;if(X)if(We())X[0]=j[0],X[1]=j[1];else{let J=1-Math.exp(-P.follow*y);X[0]+=(j[0]-X[0])*J,X[1]+=(j[1]-X[1])*J}else ie.at=[j[0],j[1]];let re=ie.at,Y=ie.trail[ie.trail.length-1];P.trail>0&&(!Y||S-Y.born>28&&Math.hypot(re[0]-Y.x,re[1]-Y.y)>.004)&&(ie.trail.push({x:re[0],y:re[1],born:S}),ie.trail.length>12&&ie.trail.shift())}ie.strength+=((j?1:0)-ie.strength)*(1-Math.exp(-y*(j?9:5)));let R=ie.trail;for(let X=R.length-1;X>=0;X--)P.trail>0&&S-R[X].born<4e3*P.trail||R.splice(X,1);Ie.fill(0);for(let X=0;X<R.length;X++){let re=R[X];Ie[3*X]=re.x,Ie[3*X+1]=re.y,Ie[3*X+2]=.55*Math.exp(-(S-re.born)/1e3/Math.max(.01,P.trail))}return ie.strength>.003||R.length>0})(g,i)||O),T==="trail"){let y=!!be?.active;O=(S=>{let P=ct();return!(!P||!P.active||(P.step(S),n.bindTexture(n.TEXTURE_2D,Le),n.texSubImage2D(n.TEXTURE_2D,0,0,0,P.width,P.height,n.RGBA,n.UNSIGNED_BYTE,P.pixels),Ke=!0,0))})(g)||O,y&&!be?.active&&(we=!0)}if((de?.live||Mt)&&(O=q(g)||O,Mt||(we=!0)),nt.length){for(let y=nt.length-1;y>=0;y--)i-nt[y].born>=2400&&nt.splice(y,1);O=!0,nt.length||(we=!0)}u&&I(),h&&(O||we||k&&i-De>=kt*li())&&(zo(),De=i,we=!1,!Qe||et&&!V||(Qe=!1,Gt())),(k||O||yt||!h)&&(Ye=!0,dr(tr))}catch(h){fn=!0,Ft(h)}};function Ae(){!Ye&&Ho()&&(Vt=performance.now(),Ye=!0,dr(tr))}let Pr=(i,m)=>{let g=e.getBoundingClientRect();if(!g.width||!g.height)return null;let h=(i-g.left)/g.width,k=(m-g.top)/g.height;return h<-.05||h>1.05||k<-.05||k>1.05?null:[h,1-k]},_r=i=>{let m=Xn(l);if(m==="none"||Yt)return $e=null,void(ie.target=null);if(he(m))return ie.target=i?[i[0],1-i[1]]:null,$e=null,void Ae();if(m==="trail"){let g=ct();return g?(i?g.move(i[0],1-i[1],l.trail.radius,performance.now()):g.leave(),$e=null,void Ae()):void 0}i?($e&&(yt=yt?{from:yt.from,to:i}:{from:$e,to:i}),$e=i,Ae()):$e=null},Xo=r.interactionTarget??window,Wo={target:Xo,move:i=>{i.type==="pointerdown"&&(function(g){if(l.tap==="none"||!V||!Ze||Yt||st||We()||g.button!==0||typeof Element<"u"&&g.target instanceof Element&&g.target.closest("button, a, input, select, summary, textarea, label"))return;let h=Pr(g.clientX,g.clientY);!h||h[0]<0||h[0]>1||h[1]<0||h[1]>1||(l.tap==="surface"?mn(h[0],1-h[1],1):(nt=[...nt,{x:h[0],y:1-h[1],born:performance.now(),strength:1}].slice(-4),Ae()))})(i);let m=Pr(i.clientX,i.clientY);Xo===window&&(Wo.inside=!!m),_r(m)},leave:()=>{$e=null,be?.leave(),ie.target&&(ie.target=null,Ae())},near:()=>Tt},nn=[fi(Wo)],Dr=()=>{let i=vn();dn(),u&&(Te=!0,we=!0),(i||we)&&Ae()},Ir=s?Vr(s.element,Dr):()=>{};nn.push(Vr(e,Dr),()=>Ir()),nn.push((function(i,m,g){if(typeof IntersectionObserver!="function")return()=>{};let h=Wr.get(m);if(!h){let O=new Map;h={observer:new IntersectionObserver(pa(O),{rootMargin:m}),watch:O},Wr.set(m,h)}let{observer:k,watch:T}=h;return ga(T,i,g)||k.unobserve(i),k.observe(i),()=>{va(T,i,g)&&k.unobserve(i),T.size||(k.disconnect(),Wr.delete(m))}})(e,"25% 0px",i=>{Tt=i.isIntersecting,Tt&&(we=!0,Ae())})),nn.push(di(()=>{document.hidden||(we=!0,Ae())})),nn.push(mi(()=>{we=!0,Ae()})),nn.push(Rn(no,i=>{let m=i.fontfaces??[],g=l.font.split(",").map(Co);m.some(h=>g.includes(Co(h.family)))&&Fr()})),ue(),nn.push(()=>{u=null,ue()});let Ur=i=>{i?.preventDefault(),mt=!0,Ye&&mr(tr),Ye=!1},Br=()=>{mt=!1,v&&(n=d.gl),D.length=0,A=null,$=null,oe=M=_=null,se=null,Fe=[],Me=[],G=null,me=!1,Le=null,be=null,Ke=!1,en=null,Jn=!1,Ve=null,de=null,Mt=!1,c=null,ce=!1,E=ve=0,Te=!0;try{_o(),we=!0,Ae()}catch(i){Ft(i)}},Vo={lost:()=>Ur(),restored:Br,rescale:()=>{vn()&&Ae()},size:()=>[B,Z],bytes:()=>{let i=b?4:8;return B*Z*4+Ln+(se?se.columns*se.rows*i*2:0)+Ne*Re*i*(me?6:Fe.length)+(be?be.width*be.height*4:0)}};v?d.join(Vo):(e.addEventListener("webglcontextlost",Ur),e.addEventListener("webglcontextrestored",Br));let Or=()=>{it&&(it.pause(),it.removeAttribute("src"),it.load(),it=null),_e&&V instanceof HTMLVideoElement&&"cancelVideoFrameCallback"in V&&V.cancelVideoFrameCallback(_e),_e=0},Gr=()=>{lt?.close(),lt=null},Ka=async i=>{let m=await createImageBitmap(i,{premultiplyAlpha:"none"}),g=[m.width,m.height],h=(function(k,T,O,y,S,P,j=8){if(!(O>=16&&y>=16&&k>0&&T>0&&S>0))return 1;let R=j/S/(P==="cover"?Math.min(k/O,T/y):Math.max(k/O,T/y));return R>.5?1:2**-Math.floor(Math.log2(1/R))})(m.width,m.height,B,Z,ge.height,l.fit);if(h===1)return{element:m,owned:!0,natural:g};try{return{element:await createImageBitmap(m,{resizeWidth:Math.max(1,Math.round(m.width*h)),resizeHeight:Math.max(1,Math.round(m.height*h)),resizeQuality:"medium",premultiplyAlpha:"none"}),owned:!0,natural:g}}finally{m.close()}},Nr=i=>new Promise((m,g)=>{let h=new Image;h.crossOrigin="anonymous",h.decoding="async",h.onload=()=>m({element:h,owned:!1}),h.onerror=()=>g(new Error("The glyph field could not load this image.")),h.src=i}),jo=(i,m,g)=>{let{element:h,owned:k}=i;if(st||g!==et)return void(k&&h instanceof HTMLVideoElement?(h.pause(),h.removeAttribute("src"),h.load()):k&&h.close());h!==V&&(Or(),Gr()),it=k&&h instanceof HTMLVideoElement?h:null,!k||h instanceof HTMLVideoElement||(lt=h);let T=h!==V;V=h,Ze=typeof m=="string"||m instanceof HTMLImageElement||m instanceof HTMLVideoElement,tt=h instanceof HTMLVideoElement?h.videoHeight:h instanceof HTMLImageElement?h.naturalHeight:h.height,ht=i.natural?.[0]??(h instanceof HTMLVideoElement?h.videoWidth:h instanceof HTMLImageElement?h.naturalWidth:h.width),ft=i.natural?.[1]??tt,hn=!0,h instanceof HTMLVideoElement&&T&&(O=>{let y=O;if(!y.requestVideoFrameCallback)return;let S=()=>{st||V!==O||(hn=!0,Ae(),_e=y.requestVideoFrameCallback(S))};_e=y.requestVideoFrameCallback(S)})(h),mt||Lr(),we=!0,Ae()},Yo=(i,m)=>{Qe&&i===et&&(Qe=!1,Gt()),Ft(m)},qr=i=>{let m=++et;if(!i)return Or(),Gr(),V=null,ht=ft=tt=Ln=0,Ze=!1,we=!0,Ae(),Promise.resolve();if((g=>!(typeof g=="string"||g instanceof HTMLImageElement&&!g.complete||g instanceof HTMLVideoElement&&g.readyState<2))(i)){try{jo({element:i,owned:!1},i,m)}catch(g){Yo(m,g)}return Promise.resolve()}return(async g=>{if(typeof g!="string")return g instanceof HTMLImageElement&&!g.complete?g.decode().then(()=>({element:g,owned:!1})):g instanceof HTMLVideoElement&&g.readyState<2?new Promise((T,O)=>{g.addEventListener("loadeddata",()=>T({element:g,owned:!1}),{once:!0}),g.addEventListener("error",()=>O(new Error("The glyph field could not load this video.")),{once:!0})}):{element:g,owned:!1};if(Pi.test(g))return new Promise((T,O)=>{let y=document.createElement("video");y.crossOrigin="anonymous",y.muted=!0,y.loop=!0,y.playsInline=!0,y.preload="auto",y.addEventListener("loadeddata",()=>{y.play().catch(()=>{}),T({element:y,owned:!0})},{once:!0}),y.addEventListener("error",()=>O(new Error("The glyph field could not load this video.")),{once:!0}),y.src=g});if(typeof createImageBitmap!="function"||typeof fetch!="function")return Nr(g);let h;try{h=await(await fetch(g).then(T=>{if(!T.ok)throw new Error("The glyph field could not load this image.");return T})).blob()}catch(T){if(T instanceof Error&&T.message.startsWith("The glyph field"))throw T;return Nr(g)}if(!/svg/i.test(h.type))try{return await Ka(h)}catch{}let k=URL.createObjectURL(h);try{return await Nr(k)}finally{URL.revokeObjectURL(k)}})(i).then(g=>jo(g,i,m),g=>Yo(m,g))};_o(),dn();let $o=r.source??null;return $o?(et=1,qr($o)):Ae(),{canvas:e,ready:Nt,get settings(){return l},update(i){let m=l,{element:g,rest:h}=o(i);if("clear"in i&&s?.element!==g?.element?(Ir(),s=g,Ir=g?Vr(g.element,Dr):()=>{}):"clear"in i&&(s=g),"clear"in i){let k=a(i.clear)?i.clear:null;k!==u&&(u=k,Te=!0,we=!0,ue(),Ae())}l=Qr(g?{...h,clear:l.clear}:h,l),dn(),i.label&&e.setAttribute("aria-label",i.label),l.maxPixelRatio!==m.maxPixelRatio&&vn(),l.charset===m.charset&&l.cellSize===m.cellSize&&l.cellAspect===m.cellAspect&&l.font===m.font&&l.fontWeight===m.fontWeight&&l.glyphScale===m.glyphScale||(Ar(),Fr()),l.levels!==m.levels&&Lo(),l.scope===m.scope||mt||(Po(),Cr=performance.now()),((!!m.fluid&&Xn(m)==="fluid")!==On()||l.fluid&&m.fluid&&l.fluid.resolution!==m.fluid.resolution)&&To(),"source"in i&&qr(i.source??null),we=!0,Ae()},setSource:qr,pointer(i,m=0){if(i===null)return void _r(null);let g=e.getBoundingClientRect();_r(Pr(g.left+i,g.top+m))},redraw(){if(!(st||mt||fn)&&B)try{Zt(!(Qe&&(v?d.canCompileInParallel:W)))&&(zo(),Qe||(we=!1))}catch(i){fn=!0,Ft(i)}},pulse(i={}){if(st||We())return;let m=e.getBoundingClientRect();if(!m.width||!m.height)return;let g=i.x??m.width/2,h=i.y??m.height/2;if(i.element){let T=i.element.getBoundingClientRect();g=T.left+T.width/2-m.left,h=T.top+T.height/2-m.top}let k=Math.max(0,Math.min(2,i.strength??1));l.tap==="surface"&&V&&Ze?mn(g/m.width,h/m.height,k):(nt=[...nt,{x:g/m.width,y:h/m.height,born:performance.now(),strength:k}].slice(-4),Ae())},play(){Yt=!1,V instanceof HTMLVideoElement&&V.play().catch(()=>{}),we=!0,Ae()},pause(){Yt=!0,V instanceof HTMLVideoElement&&V.pause()},resize(){vn()&&Ae()},destroy(){if(!st){if(st=!0,Ye&&mr(tr),Ye=!1,nn.forEach(i=>i()),v?d.leave(Vo):(e.removeEventListener("webglcontextlost",Ur),e.removeEventListener("webglcontextrestored",Br)),Or(),Gr(),V=null,!mt)if(pn(),Un(),n.deleteTexture(z),Le&&n.deleteTexture(Le),en&&n.deleteTexture(en),c&&n.deleteTexture(c),v)d.releaseAtlas($,Rr),G?.release();else{n.deleteTexture(L);for(let i of[oe,M,_])i&&n.deleteProgram(i.program);G?.dispose(),D.forEach(i=>n.deleteShader(i)),ye&&n.deleteVertexArray(ye)}$=null}}}}var so={standard:{label:"Classic ASCII",chars:" .:-=+*#%@"},asciify:{label:"Asciify",chars:" .:-=+YCIFSA#@"},minimal:{label:"Minimal",chars:" .:+"},detailed:{label:"Detailed",chars:" .,:;-~=+*xX#%@"},letters:{label:"Letters",chars:" .liLTYCFSAWM"},technical:{label:"Technical",chars:" ._:;+/>=][{}*$#@"},blocks:{label:"Tonal blocks",chars:" \u2591\u2592\u2593\u2588"},braille:{label:"Braille",chars:" \u2801\u2803\u2807\u2847\u28C7\u28E7\u28F7\u28FF"},fish:{label:"Fish",chars:" .'-,:;txoSX%#8@"},kanji:{label:"Kanji (Japanese)",chars:" \u4E00\u4E8C\u4EBA\u5C0F\u5927\u4E2D\u65E5\u672C\u76EE\u7530\u9577\u9593\u8A9E\u66F8\u66DC\u9A5A\u9727"}};function ho(e){if(e)return Object.prototype.hasOwnProperty.call(so,e)?so[e].chars:e.startsWith(" ")?e:" "+e}var Di={ascii:{mark:"glyph",charset:" .:-=+*#%@"},blocks:{mark:"glyph",charset:" \u2591\u2592\u2593\u2588"},braille:{mark:"glyph",charset:" \u2801\u2803\u2807\u2847\u28C7\u28E7\u28F7\u28FF"},dots:{mark:"dot"},lines:{mark:"glyph",charset:" -\u2550\u256A\u256C"},cross:{mark:"glyph",charset:" \xB7+xX#"},diagonal:{mark:"glyph",charset:" /\u2571\u2573"},diamond:{mark:"glyph",charset:" \xB7\u25C7\u25C8\u25C6"},mixed:{mark:"glyph",charset:" .:+/\u25C7#@"},pixel:{mark:"pixel"},mosaic:{mark:"mosaic"},lego:{mark:"lego"},voxel:{mark:"voxel"},disco:{mark:"disco"},dither:{mark:"dither"},hex:{mark:"hex"},led:{mark:"led"},cmyk:{mark:"cmyk"},stipple:{mark:"stipple"},engraving:{mark:"engraving"},crosshatch:{mark:"crosshatch"},woodblock:{mark:"woodblock"},risograph:{mark:"risograph"},pointillism:{mark:"pointillism"}};var Ii=/\p{L}/u,Ui=new Set(Object.values(so).map(e=>e.chars));var Bi=new Set(["glyph","inlay"]),jn=e=>Bi.has(e??"glyph"),Oi=e=>({cellSize:Math.max(7,e.cellSize??8),cellAspect:.62,glyphScale:.9}),Da=new WeakSet,Ia=e=>{Da.add(e)},fo=e=>e&&!Da.has(e)?e.current.charset:void 0;function mo(e,r){let t=ho(r);if(!t)return e;if(jn(e.mark))return{...e,charset:t,...uo(t,e)};let o={...e,...Oi(e)};return{...o,mark:"glyph",charset:t,...uo(t,o)}}var vr=null;var Sa=new Set;var Fa=12,je=new Set,It=null,$n=null,yr=0,Yn=-1e9,Mr=0,wr=0,ao=!1,io=!1,Gi=()=>{let e=$n?.timeline?.currentTime;return typeof e=="number"?e:null};var lo=()=>typeof performance<"u"?performance.now():Date.now(),po=()=>typeof innerHeight=="number"?innerHeight:0;function Er(e,r=e.getBoundingClientRect()){if(e.isConnected===!1||typeof e.getClientRects=="function"&&e.getClientRects().length===0)return 1/0;let t=r.bottom<0?-r.bottom:r.top-po();return t>0?t:0}function Ni(){try{let e=$n?.querySelectorAll?.("dialog:modal");return e?.length?e[e.length-1]:null}catch{return null}}var qi=1e8;function Ua(e,r){if(e.eager)return void(e.wanted=!0);let t=po(),o=Er(e.host,r);!t||o<=2*t?e.wanted=!0:o>3*t&&(e.wanted=!1)}function zi(e){let r=!1;for(let t of e)if(t?.target)for(let o of je)o.host===t.target&&(Ua(o,t.boundingClientRect??void 0),r=!0);r&&Fn()}var Ca=()=>Fn(),kr=0,br=0,La=()=>{let e=typeof scrollY=="number"?scrollY:0;e!==br&&(kr=e>br?1:-1),br=e};function Hi(e,r){return!r||!kr||e.getBoundingClientRect().top>0==kr>0?r:2*r}var xr=null,Ba=e=>{xr!==e&&(xr?.removeEventListener?.("close",Ca,!0),xr?.removeEventListener?.("scroll",La,!0),e?.addEventListener?.("close",Ca,!0),e?.addEventListener?.("scroll",La,{capture:!0,passive:!0}),xr=e)},co=new WeakSet,An=0;function go(){An||typeof requestIdleCallback!="function"||(An=requestIdleCallback(Xi,{timeout:2e3}))}function Xi(e){An=0;let r=[...je].filter(t=>!t.live&&t.prewarm&&!co.has(t)).sort((t,o)=>Er(t.host)-Er(o.host));for(let t of r){if(e.timeRemaining()<2&&!e.didTimeout)return void go();co.add(t);try{t.prewarm()}catch{}}}function Wi(e){$n!==e.doc&&($n=e.doc,je.clear(),yr=Mr=wr=kr=0,Yn=-1e9,br=typeof scrollY=="number"?scrollY:0),Ba($n),je.add(e);let r=(function(){let t=typeof IntersectionObserver=="function"?IntersectionObserver:null;if(!t)return null;if(It?.ctor!==t){It?.list.forEach(o=>o.disconnect()),It={ctor:t,list:["200% 0px","300% 0px","0px"].map(o=>new t(zi,{rootMargin:o}))};for(let o of je)It.list.forEach(a=>a.observe(o.host))}return It.list})();r?.forEach(t=>t.observe(e.host)),r?Ua(e):e.wanted=!0,Fn(),e.live||go()}function Fn(e=!1){if(ao)io=!0;else{ao=!0;try{do{io=!1;let r=lo(),t=Gi();(e||(t===null?r-Yn>16||r<Yn:t!==Yn))&&(Yn=t??r,Mr=wr=0);for(let n of je)n.host.isConnected===!1&&(n.wanted=!1);for(let n of je)n.live&&!n.wanted&&n.release();let o=[...je].filter(n=>n.live&&!n.shared),a=Ni(),s=n=>!!a&&!a.contains(n.host),u=n=>Er(n.host)+(s(n)?qi:0),l=n=>n.eager&&!s(n),f=()=>o.filter(n=>n.live&&!n.shared).map(n=>[n,u(n)+(l(n)?0:1e9)]).sort((n,b)=>b[1]-n[1]);for(let n=o.length-Fa,b=n>0?f():[];n>0;n--)b.shift()?.[0].release();let p=xa(),d=1*po(),x=()=>[...je].filter(n=>n.live&&n.shared&&u(n)>d).sort((n,b)=>u(b)-u(n));if(p?.overBudget)for(let n of x()){if(!p.overBudget)break;n.release()}let v=[...je].filter(n=>n.wanted&&!n.live).map(n=>[n,n.eager?-1:u(n)]).map(([n,b])=>[n,b,b>0?Hi(n.host,b):b]).sort((n,b)=>n[2]-b[2]),w=0;for(let[n,b]of v){if(!je.has(n)||n.live)continue;if(p&&!p.roomy){let L=x()[0];if(!L||u(L)<=u(n)||(L.release(),!p.roomy))break}if(!n.eager&&(Mr>=4||wr>=2)&&(!e||w)){yr||(yr=requestAnimationFrame(()=>{yr=0,Fn(!0)}));break}if(o.filter(L=>L.live&&!L.shared).length>=Fa){let L=f()[0]?.[0];if(!L||(l(L)?!n.eager||u(L)<=u(n):!n.eager&&u(L)<=b))break;L.release()}let W=lo();n.mount(),Mr+=lo()-W,w++,n.eager||wr++,n.live&&!n.shared&&o.push(n)}}while(io)}finally{ao=!1}}}var Oa='ui-monospace, "SF Mono", Menlo, Consolas, monospace',Pa=new Map,Vi=".:-=+*#%@";function ji(e,r=Oa){let t=`${r}\0${e}`,o=Pa.get(t);if(o)return o;let a={max:1,mean:1};try{let s=typeof document>"u"?null:Object.assign(document.createElement("canvas"),{width:48,height:48}).getContext("2d",{willReadFrequently:!0});if(s&&typeof s.getImageData=="function"){s.font=`500 36px ${r}`,s.textAlign="center",s.textBaseline="middle";let u=v=>{s.clearRect(0,0,48,48),s.fillStyle="#000",s.fillText(v,24,25);let w=s.getImageData(0,0,48,48).data,n=0;for(let b=3;b<w.length;b+=4)n+=w[b];return n/255},l=v=>[...v].filter(w=>w.trim()).map(u),f=v=>v.reduce((w,n)=>w+n,0)/Math.max(1,v.length),p=l(e),d=l(Vi),x=u("@");p.length&&x>0&&f(d)>0&&(a={max:Math.max(...p)/x,mean:f(p)/f(d)})}}catch{}return Pa.set(t,a),a}function uo(e,r){let{max:t,mean:o}=ji(e,r.font??Oa),a=r.glyphScale??.8,s=r.gamma??1,u=r.fontWeight??500;return t>1.15?{glyphScale:Math.max(.3,a*Math.max(.62,t**-.36)),gamma:s,fontWeight:u}:o>1.5?{glyphScale:Math.max(.3,a*o**-.25),gamma:s,fontWeight:u}:t<.85?{glyphScale:Math.min(1.6,a*Math.min(1.3,t**-.3)),gamma:s,fontWeight:t<.6?Math.max(u,700):u}:{glyphScale:a,gamma:s,fontWeight:u}}var Sn=new WeakMap;function vo(e,r){for(let t of Sn.get(e)?.keys()??[])t.getAttribute("src")!==r&&(t.src=r)}function xo(e){let r=Sn.get(e);Sn.delete(e),r?.forEach(t=>t())}function yo(e,r,t,o,a){let s=document.createElement("img");s.alt="",s.decoding="async",s.setAttribute("aria-hidden","true"),s.setAttribute("style",`${t};object-fit:cover`),s.style.opacity="1",s.dataset.asciiPoster="",s.src=r;let u=e.style.getPropertyValue("position"),l=typeof getComputedStyle=="function"&&getComputedStyle(e).position==="static";l&&e.style.setProperty("position","relative");let f=e.style.getPropertyValue("isolation"),p=/z-index:\s*-1/.test(t)&&typeof getComputedStyle=="function"&&getComputedStyle(e).isolation==="auto";p&&e.style.setProperty("isolation","isolate"),a?.parentElement===e?e.insertBefore(s,a):e.appendChild(s);let d=!1,x=()=>{d||(d=!0,s.remove(),Sn.get(o)?.delete(s),l&&(u?e.style.setProperty("position",u):e.style.removeProperty("position")),p&&(f?e.style.setProperty("isolation",f):e.style.removeProperty("isolation")))},v=Sn.get(o)??new Map;return v.set(s,x),Sn.set(o,v),{show(w){s.style.opacity=w?"1":"0"},remove:x}}function _a(e){let r=document.createElement("canvas");for(let t of e.getAttributeNames?.()??[])t!=="width"&&t!=="height"&&r.setAttribute(t,e.getAttribute(t));return r.style.cssText=e.style.cssText,Object.assign(r.dataset,e.dataset),e.replaceWith?e.replaceWith(r):e.parentElement&&(e.parentElement.insertBefore(r,e),e.remove()),r}function Ga(e){let{host:r,kit:t}=e,o,a=e.canvas,s=null,u=!1,l=!1,f=!1,p=!1,d={},x={},v=e.source,w=!1,n={},b=null,W=null,L=!1,z=null,oe=()=>{},M=!e.ownPoster&&t?.current.poster?yo(r,t.current.poster,e.place,t,a):null,_=()=>{if(!vr||t?.current.globalLook===!1||t?.current.charset||!jn(x.mark)&&!e.glyphs||x.glyphOrder!=="scatter"&&!Ui.has(x.charset??"")&&Ii.test(x.charset??""))return;let A=vr.style?Di[vr.style]:void 0,D=A?.mark??(jn(x.mark)?x.mark??"glyph":"glyph"),B=jn(D)?vr.charset||(A&&"charset"in A?A.charset:void 0):void 0;return A||B?{mark:D,charset:B}:void 0},$=()=>({...e.glyphs?Object.fromEntries(Object.keys(e.glyphs()).map(A=>[A,x[A]]).filter(([,A])=>A!==void 0)):{},mark:x.mark??"glyph",charset:x.charset??" .,:-=+*#%@",glyphScale:x.glyphScale??.8,gamma:x.gamma??1,fontWeight:x.fontWeight??500}),se=A=>{if(!A.charset)return{...$(),mark:A.mark};let D=e.glyphs&&!jn(x.mark)?e.glyphs():{};return{...D,mark:A.mark,charset:A.charset,...uo(A.charset,{...x,...D})}},Fe=()=>{let A=_(),D=A&&`${A.mark}\0${A.charset??""}`;return D===o?null:(o=D,A?se(A):$())},Me={host:r,doc:document,eager:t?.current.lazy===!1,wanted:!1,live:!1,poster:!!M||!!e.ownPoster,mount(){if(l||s)return;u&&(a=e.canvas=_a(a)),u=!0,x={...e.options(),...d},o=void 0;let A=Fe(),D;try{D=Aa(a,{...x,...A,...v===void 0?{}:{source:v},onError:()=>{s===D&&G()}})}catch{return void G()}s=D,Me.live=!0,Me.shared=Ma(a);let B=a;if(Me.shared)oe=()=>{};else{let Z=0,ae=()=>{s===D&&(M?.show(!0),clearTimeout(Z),Z=setTimeout(()=>{s===D&&a===B&&(Me.release(),Fn())},1e3))},Be=()=>{clearTimeout(Z),requestAnimationFrame(()=>requestAnimationFrame(()=>{s===D&&M?.show(!1)}))};B.addEventListener?.("webglcontextlost",ae),B.addEventListener?.("webglcontextrestored",Be),oe=()=>{clearTimeout(Z),B.removeEventListener?.("webglcontextlost",ae),B.removeEventListener?.("webglcontextrestored",Be)}}w&&D.pause(),D.ready.then(()=>{s===D&&(L=!0,M?.show(!1),b?.(),b=W=null)},()=>{}),e.onMount?.(D,a)},release(){if(!s)return;let A=s;s=null,Me.live=!1,L=!1,oe(),z?.clear(),z=null,n=A.settings,A.destroy(),Me.shared?l||(a.width=a.width,u=!1):((D=>{try{let B=D.getContext("webgl2");B&&!B.isContextLost?.()&&B.getExtension("WEBGL_lose_context")?.loseContext()}catch{}})(a),l||(a=e.canvas=_a(a),u=!1)),M?.show(!0),e.onRelease?.()},prewarm(){if(l||s)return;x={...e.options(),...d};let A=_();Ra(a,{...x,...A?se(A):{}})}};function G(){f||(f=!0,me(),p||e.onFail())}function me(){l||(l=!0,Me.release(),(function(A){je.delete(A)&&([...je].some(D=>D.host===A.host)||It?.list.forEach(D=>D.unobserve(A.host)),!je.size&&It&&(It.list.forEach(D=>D.disconnect()),It=null),je.size||(Ba(null),An&&typeof cancelIdleCallback=="function"&&cancelIdleCallback(An),An=0),Fn())})(Me),Sa.delete(ye),a.remove(),f?M?.show(!0):M?.remove())}let ye={relook(){s||(ae=>{co.delete(ae),je.has(ae)&&go()})(Me);let A=Fe();if(!A||!s)return;let D=s,B=L&&!(t?.current.reducedMotion??(typeof matchMedia=="function"&&matchMedia("(prefers-reduced-motion: reduce)").matches));z?.clear(),z=null,B&&(D.redraw(),z=(function(ae,Be){if(!ae.width||!ae.height||typeof document>"u")return null;let ge=document.createElement("canvas");ge.width=ae.width,ge.height=ae.height;let Ge=ge.getContext("2d");if(!Ge||typeof ge.animate!="function")return null;try{Ge.drawImage(ae,0,0)}catch{return null}ge.setAttribute("aria-hidden","true"),ge.dataset.asciiSweep="",ge.setAttribute("style",Be);let Ne=document.createElement("span"),Re,Xe;Ne.setAttribute("aria-hidden","true"),Ne.dataset.asciiSweep="",Ne.setAttribute("style",`${Be};right:auto;width:2px;margin-left:-1px;opacity:0;background:var(--ascii-sweep, #f3ba32);box-shadow:0 0 10px 1px color-mix(in srgb, var(--ascii-sweep, #f3ba32) 40%, transparent)`),ae.after(ge,Ne);let V=()=>{Re?.cancel(),Xe?.cancel(),ge.remove(),Ne.remove()};return{clear:V,reveal(){if(!ge.isConnected)return;let Ze={duration:200,delay:40,easing:"cubic-bezier(.23,1,.32,1)",fill:"both"};Re=ge.animate([{clipPath:"inset(0% 0% 0% 0%)"},{clipPath:"inset(0% 0% 0% 100%)"}],Ze);let it=ae.clientWidth||ae.getBoundingClientRect().width;Xe=Ne.animate([{transform:"translateX(0px)",opacity:.35},{opacity:.35,offset:.7},{transform:`translateX(${it}px)`,opacity:0}],Ze),Re.onfinish=V}}})(a,e.place)),D.update(A);let Z=z;Z&&requestAnimationFrame(()=>requestAnimationFrame(()=>{z===Z&&s===D?Z.reveal():Z.clear()}))}};return{field:{get canvas(){return a},get ready(){return s?s.ready:W??(W=new Promise(A=>{b=A}))},get settings(){return s?.settings??n},update(A){if(d={...d,...A},x={...x,...A},!s)return;let D=Fe(),B=_();s.update(B?{...A,...se(B)}:D?{...A,...D}:A)},setSource:A=>(v=A,s?s.setSource(A):Promise.resolve()),pointer(A,D){s?.pointer(A,D)},redraw(){s?.redraw()},pulse(A){s?.pulse(A)},play(){w=!1,s?.play()},pause(){w=!0,s?.pause()},resize(){s?.resize()},destroy(){me()}},get canvas(){return a},get live(){return!!s},get failed(){return f},start(){Sa.add(ye),p=!0;try{Wi(Me)}finally{p=!1}},destroy:me}}var Yi=(e,r=0,t=1)=>Math.min(t,Math.max(r,e));var Ut,Tr=()=>typeof matchMedia=="function"&&matchMedia("(prefers-reduced-motion: reduce)").matches;var Mo={scene:"none",background:"transparent",color:"ink",levels:"none",fit:"cover",focus:{x:.5,y:.5},vignette:0,drift:0,hover:"none",shade:0,contrast:1,brightness:0,gamma:1,maxPixelRatio:2,clear:!1};function Kn(e,r,t){let o=(e??"").trim(),a=/^var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)$/.exec(o);if(a?o=Na(r,a[1])||(a[2]??"").trim():o.startsWith("--")&&(o=Na(r,o)),!o)return t?Kn(t,r):null;if(/^#[\da-f]{6}$/i.test(o))return o.toLowerCase();if(/^#[\da-f]{3}$/i.test(o))return`#${[...o.slice(1)].map(p=>p+p).join("")}`.toLowerCase();let s=/^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(o);if(s)return qa([+s[1],+s[2],+s[3]]);if(Ut===void 0)try{Ut=typeof document>"u"?null:Object.assign(document.createElement("canvas"),{width:1,height:1}).getContext("2d",{willReadFrequently:!0})}catch{Ut=null}if(!Ut)return t?Kn(t,r):null;Ut.clearRect(0,0,1,1),Ut.fillStyle="#000",Ut.fillStyle=o,Ut.fillRect(0,0,1,1);let[u,l,f]=Ut.getImageData(0,0,1,1).data;return qa([u,l,f])}var Na=(e,r)=>typeof getComputedStyle=="function"?getComputedStyle(e).getPropertyValue(r).trim():"",qa=e=>`#${e.map(r=>Math.round(Yi(r,0,255)).toString(16).padStart(2,"0")).join("")}`,$i=e=>{let r=parseInt(e.slice(1,7),16);return[r>>16&255,r>>8&255,255&r]};function wo(e){let r=typeof getComputedStyle=="function"?getComputedStyle(e):null,t=/^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?/i.exec(r?.backgroundColor??"");if(t&&(t[4]===void 0?1:t[4].endsWith("%")?parseFloat(t[4])/100:parseFloat(t[4]))>=.5)return .2126*+t[1]+.7152*+t[2]+.0722*+t[3]<128;let o=Kn(r?.color??"",e);if(!o)return typeof matchMedia=="function"&&matchMedia("(prefers-color-scheme: dark)").matches;let[a,s,u]=$i(o);return .2126*a+.7152*s+.0722*u>140}function za(){let e=[];return{set(r,t,o){e.some(([a,s])=>a===r&&s===t)||e.push([r,t,r.style.getPropertyValue(t)]),r.style.setProperty(t,o)},restore(){for(let[r,t,o]of e.reverse())o?r.style.setProperty(t,o):r.style.removeProperty(t);e.length=0}}}function bo(e,r){let t={...e,...r},o=e.look,a=r.look;return a&&(t.look=Object.fromEntries(Object.entries({...o,...a}).filter(([,s])=>s!==void 0))),t}var cn=(e,r,t,o)=>typeof e=="number"&&Number.isFinite(e)?Math.min(o,Math.max(t,e)):r;function Ha(e){return e==="dots"?" \xB7\u2219\u2022\u25CF":ho(e)}function Eo(e,r){if(!r||!r.preset||typeof r.preset.mount!="function")throw new TypeError("background() needs a preset, such as `aurora` imported from asciify-engine/kit.");let t=r.preset,o=r.poster,a=M=>({...M,poster:M.preset===t?o:void 0}),s={current:a({...r})};Ia(s);let u=null,l=!1,f=!1,p=new Set,d=()=>{let M=s.current,_=M.preset;return{speed:cn(M.speed,_.speed,0,5),cellSize:cn(M.cellSize,_.cellSize,3,96),charset:Ha(M.charset),cursor:M.look?.hover!=="none"&&(M.cursor??_.cursor),tap:M.tap==="ring"||M.tap==="surface"?M.tap:void 0,mark:M.mark==="glyph"||M.mark==="dot"?M.mark:void 0,clear:M.clear??!1,clearMap:{padding:cn(M.clearPadding,8,0,400),softness:cn(M.clearSoftness,28,0,600),strength:cn(M.clearStrength,.85,0,1)},dither:cn(M.dither,0,0,1),accent:M.accent,text:M.text?.trim()||"ASCIIFY",look:M.look}},x=M=>{let _=s.current,$=_.palette;return(typeof $=="string"?$:$?.[M?"dark":"light"])??_.color??_.ink},v=()=>String(cn(s.current.opacity,s.current.preset.opacity??1,0,1)),w=()=>!!(s.current.reducedMotion??Tr()),n=M=>{let _=null;if(_=s.current.preset.mount({host:e,kit:s,settings:d,ink:x,reducedMotion:()=>s.current.reducedMotion,onFail:()=>{u===_&&(u=null)}}),!_)return null;let $=_.canvas.style;return M&&($.opacity="0",$.transition="opacity 320ms cubic-bezier(.16, 1, .3, 1)",_.canvas.offsetWidth),$.opacity=v(),l&&_.pause(),_},b={position:e.style.getPropertyValue("position"),isolation:e.style.getPropertyValue("isolation")},W=(M,_)=>{_?e.style.setProperty(M,_):e.style.removeProperty(M)},L=!1,z=M=>{L=!0,M.destroy(),u&&!f&&(typeof getComputedStyle=="function"&&getComputedStyle(e).position==="static"&&e.style.setProperty("position","relative"),e.style.setProperty("isolation","isolate"))},oe=M=>{if(f||!M||typeof M.mount!="function"||M===s.current.preset)return;s.current=a({...s.current,preset:M});let _=u;u=n(!!_&&!w()),_&&($=>{if(w())return void z($);$.canvas.style.transition="opacity 320ms cubic-bezier(.16, 1, .3, 1)",$.canvas.style.opacity="0";let se={run:$,timer:setTimeout(()=>{p.delete(se),z($)},340)};p.add(se)})(_)};return u=n(!1),{get supported(){return!!u&&!f},get field(){return f?null:u?.field??null},get preset(){return s.current.preset},update(M){if(f||!M)return;let{preset:_,...$}=M;"poster"in $&&(o=$.poster),s.current=a(bo(s.current,$)),$.poster&&s.current.poster&&vo(s,$.poster),_&&_!==s.current.preset?oe(_):u&&(u.canvas.style.opacity=v(),u.refresh())},play(){!f&&l&&(l=!1,u?.play())},pause(){f||(l=!0,u?.pause())},setPreset:oe,destroy(){if(!f){f=!0;for(let M of p)clearTimeout(M.timer),M.run.destroy(),L=!0;p.clear(),u?.destroy(),u=null,L&&(W("position",b.position),W("isolation",b.isolation)),xo(s)}}}}function Xa(e,r,t=!1){let o=e.clear;return typeof o=="function"||Array.isArray(o)?{rects:o,...e.clearMap}:o?{element:o,...r}:t}function Wa(e){let{host:r,layer:t="under",kit:o}=e;if(typeof document>"u")return null;let a=`position:absolute;inset:0;width:100%;height:100%;pointer-events:none;border-radius:inherit;z-index:${t==="under"?-1:"auto"}`;if(!gr())return o?.current.poster&&!e.ownPoster&&yo(r,o.current.poster,a,o),null;let s=za(),u=document.createElement("canvas");getComputedStyle(r).position==="static"&&s.set(r,"position","relative"),t==="under"&&s.set(r,"isolation","isolate"),u.dataset.asciiKit="",u.setAttribute("style",a),r.appendChild(u);let l=wo(r),f=!1,p=()=>{let z=e.reducedMotion();return z===!0?{speed:0,drift:0,respectReducedMotion:!0}:{respectReducedMotion:z!==!1}},d=()=>Kn(e.ink(l),r,l?"#d8d6cf":"#1d1d1b")??"#888888",x=Ga({host:r,canvas:u,kit:o,place:a,ownPoster:e.ownPoster,glyphs:e.glyphs,source:e.source??null,options:()=>({...mo({...Mo,...e.look(l)},fo(o)),...p(),ink:d(),interactionTarget:r,label:e.label??""}),onMount:(z,oe)=>{e.label||(oe.removeAttribute("role"),oe.removeAttribute("aria-label"),oe.setAttribute("aria-hidden","true")),e.onMount?.()},onRelease:e.onRelease,onFail:()=>{L(),e.onFail?.()}}),v=x.field,w=!1,n=()=>{f||(l=wo(r),v.update({...mo({...Mo,...e.look(l)},fo(o)),...p(),ink:d()}))},b=()=>{w=!1,n()},W=ma(()=>{w||f||(w=!0,dr(b))});function L(){f||(f=!0,w&&mr(b),W(),x.destroy(),s.restore())}return x.start(),x.failed?(L(),null):{field:v,get canvas(){return x.canvas},get live(){return x.live},dark:()=>l,still:()=>!!(e.reducedMotion()??Tr()),refresh:n,destroy:L}}var Ki=(e,r)=>e.cursor===!1?"none":typeof e.cursor=="string"?e.cursor:r;function Qi(e,r,t,o){let a=null;if(a=Wa({host:e.host,kit:e.kit,layer:"under",glyphs:o&&(()=>o(e.settings())),look:u=>{let l=e.settings();return{...r(l,u),...l.look}},ink:u=>e.ink(u)??(u?t.dark:t.light),reducedMotion:e.reducedMotion,onFail:()=>{a=null,e.onFail()}}),!a)return null;let s=a.canvas;return{get field(){return a?.field??null},get canvas(){return a?.canvas??s},refresh(){a?.refresh()},play(){a?.field.play()},pause(){a?.field.pause()},destroy(){a?.destroy(),a=null}}}var ja=()=>typeof innerWidth=="number"&&innerWidth<760,Ji={light:"#86847e",dark:"#7c7a74"},Ya={light:"#8f8d86",dark:"#64625d"},Zi=(e,r)=>e.mark??(e.charset||e.look?.charset?"glyph":r),Va=e=>({font:'"Geist Mono", ui-monospace, "SF Mono", Menlo, monospace',fontWeight:400,cellSize:e.cellSize,cellAspect:.62,glyphScale:.86}),el=e=>({cellSize:e.cellSize,cellAspect:1,dotScale:.68}),tl={x:.18,y:.2,width:.64,height:.6,feather:.3,shape:"ellipse"};function $a(e){let{scene:r,charset:t,hover:o,middle:a=tl,feather:s=.3,graphite:u=Ji}=e,l=e.mark??"glyph";return{id:e.id,name:e.name,description:e.description,cellSize:e.cellSize,speed:e.speed??1,cursor:e.cursor??!0,opacity:e.opacity,mount(f){let p=Qi(f,(v,w)=>{let n=Zi(v,l);return{scene:r,color:"ink",shade:0,background:"transparent",vignette:0,speed:v.speed,maxPixelRatio:2,levels:"none",blend:"on",...n==="dot"?{mark:"dot",...el(v)}:{mark:"glyph",charset:v.charset??t,...Va(v)},hover:Ki(v,o),lantern:{radius:.14,strength:.45,trail:.8,follow:9},trail:{strength:.8,radius:.35},fluid:{radius:.09,refraction:.03,glow:.6},clear:Xa(v,{padding:0,feather:s,shape:"ellipse"},a),...e.tune?.(v,w)}},u,l==="dot"?v=>({...Va(v),charset:t}):void 0);if(!p||!e.extra)return p;let d=e.extra(f,p),x=p.destroy.bind(p);return Object.assign(p,{destroy(){d(),x()}})}}}var ko=$a({id:"swell",name:"Swell",description:"A fine grid that swells in slow rolling waves, quiet in the middle. Dots by default, or characters.",cellSize:10,opacity:.6,scene:"swell",mark:"dot",charset:" .:-=+*#",hover:"lantern",graphite:Ya,tune:()=>({scale:ja()?1.5:1,contrast:.62,brightness:-.19,blend:"auto",lantern:{radius:.12,strength:.5,trail:1,follow:8},trail:{strength:.7,radius:.35}})});var Cn=document.querySelector("[data-asciify-background]");if(Cn instanceof HTMLElement)if(gr()){let e=document.querySelector(".hero"),r=null;try{r=Eo(Cn,{preset:ko,palette:"#8f8d86",speed:1,cellSize:10,opacity:.6,mark:"dot",cursor:"lantern",clear:e instanceof HTMLElement?e:!1,globalLook:!0})}catch{Cn.dataset.asciifyState="failed"}if(r){Cn.dataset.asciifyState=r.supported?"ready":"fallback";let t=!1,o=()=>{t||(t=!0,r.destroy(),Cn.dataset.asciifyState="destroyed")};window.addEventListener("pagehide",a=>{a.persisted||o()})}}else Cn.dataset.asciifyState="fallback";})();
