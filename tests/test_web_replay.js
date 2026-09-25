const {JSDOM}=require("jsdom"); const fs=require("fs");
const html=fs.readFileSync("/home/user/heisenbug/web/index.html","utf8");
const session=JSON.parse(fs.readFileSync("/home/user/heisenbug/web/session.json","utf8"));
const errors=[];

const dom=new JSDOM(html,{
  runScripts:"dangerously", pretendToBeVisual:true, url:"https://example.com/",
  beforeParse(w){
    w.fetch=()=>Promise.resolve({json:()=>Promise.resolve(session)});
    w.addEventListener("error",e=>errors.push("onerror: "+e.message));
  }
});
process.on("uncaughtException",e=>errors.push("uncaught: "+e.message));

setTimeout(()=>{
  const d=dom.window.document, btn=d.getElementById("go");
  console.log("after load -> button enabled:", !btn.disabled);
  console.log("capdate :", JSON.stringify(d.getElementById("capdate").textContent));
  console.log("cfg     :", d.getElementById("cfg").textContent.slice(0,80));
  btn.onclick();
  console.log("clicked -> label:", btn.textContent);
  setTimeout(()=>{
    const log=d.getElementById("log"), mx=d.getElementById("matrix"), fd=d.getElementById("findings");
    console.log("\nlog lines    :", log.children.length);
    console.log("matrix rows  :", mx.querySelectorAll("tbody tr").length);
    console.log("finding cards:", fd.querySelectorAll(".card").length);
    console.log("report blocks:", fd.querySelectorAll(".report").length);
    console.log("button label :", btn.textContent, "| enabled:", !btn.disabled);
    console.log("signatures:");
    [...mx.querySelectorAll("tbody tr")].forEach(r=>{
      const td=r.querySelectorAll("td");
      console.log("   ", td[0].textContent.trim().padEnd(26),
                  td[4]?td[4].textContent.trim():"-", "|",
                  td[5]?td[5].textContent.trim():"-");
    });
    console.log("\n"+(errors.length? "JS ERRORS:\n  "+errors.join("\n  ") : "NO JS ERRORS"));
    process.exit(errors.length?1:0);
  }, 17000);
}, 800);
