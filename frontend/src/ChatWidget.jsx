import{useState}from'react';
import{api}from'./api';

const INTENTS=[
  {id:'why',label:'Mengapa risikonya tinggi?',icon:'⚠️'},
  {id:'intervention',label:'Apa saran intervensinya?',icon:'💡'},
  {id:'changes',label:'Apa yang berubah?',icon:'📊'},
  {id:'confidence',label:'Seberapa yakin model?',icon:'🎯'},
];

export default function ChatWidget({predictionId,onClose}){
  const[messages,setMessages]=useState([{role:'assistant',text:'Halo! Saya asisten SPRAM. Pilih pertanyaan di bawah atau ketik sendiri.'}]);
  const[loading,setLoading]=useState(false);
  const[input,setInput]=useState('');

  async function ask(intent){
    const label=INTENTS.find(i=>i.id===intent)?.label||intent;
    setMessages(m=>[...m,{role:'user',text:label}]);
    setLoading(true);
    try{
      const data=await api('/assistant',{method:'POST',body:JSON.stringify({prediction_id:predictionId,intent})});
      setMessages(m=>[...m,{role:'assistant',text:data.answer,disclaimer:data.disclaimer}]);
    }catch(e){
      setMessages(m=>[...m,{role:'assistant',text:'Gagal menghubungi asisten. Coba lagi.'}]);
    }
    setLoading(false);
  }

  function handleFreeText(e){
    e.preventDefault();
    if(!input.trim())return;
    const t=input.trim().toLowerCase();
    const match=t.includes('risiko')||t.includes('tinggi')||t.includes('mengapa')||t.includes('kenapa')?'why':
      t.includes('saran')||t.includes('intervensi')||t.includes('tindak')?'intervention':
      t.includes('berubah')||t.includes('ubah')||t.includes('banding')?'changes':
      t.includes('yakin')||t.includes('confidence')||t.includes('akurat')?'confidence':null;
    setInput('');
    if(match){ask(match)}
    else{
      setMessages(m=>[...m,{role:'user',text:input.trim()},{role:'assistant',text:'Pertanyaan ini belum didukung oleh asisten. Silakan pilih dari opsi yang tersedia atau hubungi tim akademik.',disclaimer:'Penjelasan bukan bukti sebab-akibat dan bukan keputusan otomatis.'}]);
    }
  }

  return(
    <div style={{position:'fixed',bottom:24,right:24,width:380,maxHeight:'70vh',background:'#fff',borderRadius:12,boxShadow:'0 8px 32px rgba(11,31,58,.18)',display:'flex',flexDirection:'column',zIndex:1000,border:'1px solid #e2e8f0'}}>
      <div style={{background:'#0B1F3A',color:'#fff',padding:'14px 18px',borderRadius:'12px 12px 0 0',display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <span style={{fontWeight:600,fontSize:15}}>🤖 Asisten SPRAM</span>
        <button onClick={onClose} style={{background:'none',border:'none',color:'#fff',fontSize:18,cursor:'pointer',padding:0}}>✕</button>
      </div>
      <div style={{flex:1,overflowY:'auto',padding:14,display:'flex',flexDirection:'column',gap:10,maxHeight:'45vh'}}>
        {messages.map((m,i)=>(
          <div key={i} style={{alignSelf:m.role==='user'?'flex-end':'flex-start',maxWidth:'85%'}}>
            <div style={{background:m.role==='user'?'#0B1F3A':'#F1F5F9',color:m.role==='user'?'#fff':'#1e293b',padding:'10px 14px',borderRadius:10,fontSize:14,lineHeight:1.5}}>
              {m.text}
            </div>
            {m.disclaimer&&<div style={{fontSize:11,color:'#94a3b8',marginTop:4,fontStyle:'italic'}}>{m.disclaimer}</div>}
          </div>
        ))}
        {loading&&<div style={{alignSelf:'flex-start',color:'#94a3b8',fontSize:13}}>Mengetik...</div>}
      </div>
      <div style={{padding:'10px 14px',borderTop:'1px solid #e2e8f0'}}>
        <div style={{display:'flex',flexWrap:'wrap',gap:6,marginBottom:10}}>
          {INTENTS.map(i=>(
            <button key={i.id} onClick={()=>ask(i.id)} disabled={loading}
              style={{fontSize:12,padding:'6px 10px',borderRadius:6,border:'1px solid #cbd5e1',background:'#f8fafc',cursor:'pointer',color:'#334155',whiteSpace:'nowrap'}}>
              {i.icon} {i.label}
            </button>
          ))}
        </div>
        <form onSubmit={handleFreeText} style={{display:'flex',gap:8}}>
          <input value={input} onChange={e=>setInput(e.target.value)} placeholder="Ketik pertanyaan..." disabled={loading}
            style={{flex:1,padding:'8px 12px',borderRadius:8,border:'1px solid #cbd5e1',fontSize:14,outline:'none'}}/>
          <button type="submit" disabled={loading||!input.trim()}
            style={{padding:'8px 14px',borderRadius:8,border:'none',background:'#0B1F3A',color:'#fff',fontSize:14,cursor:'pointer'}}>↵</button>
        </form>
      </div>
    </div>
  );
}
