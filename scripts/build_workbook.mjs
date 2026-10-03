import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.resolve(import.meta.dirname,'..');
const output=path.join(root,'outputs','processed-workbook');
await fs.mkdir(output,{recursive:true});
await fs.mkdir(path.join(output,'qa'),{recursive:true});
const tabs=JSON.parse(await fs.readFile(path.join(root,'data/workbook_data.json'),'utf8'));
const workbook=Workbook.create();
for(const [name,input]of Object.entries(tabs)){
  const sheet=workbook.worksheets.add(name);sheet.showGridLines=false;
  const columns=Math.max(...input.map(r=>r.length));
  const rows=input.map(r=>Array.from({length:columns},(_,i)=>{let v=r[i]??null;if(typeof v==='string'&&v.startsWith('='))v="'"+v;return v;}));
  const area=sheet.getRangeByIndexes(0,0,rows.length,columns);area.values=rows;
  area.format.font={name:'Arial',size:11,color:'#253D32'};
  area.format.rowHeight=40;area.format.columnWidth=26;area.format.wrapText=true;area.format.verticalAlignment='center';
  const header=sheet.getRangeByIndexes(0,0,1,columns);header.format.fill='#233D32';header.format.font={name:'Arial',size:11,bold:true,color:'#FFFFFF'};header.format.rowHeight=42;
  if(name==='00_Read_Me'){
    sheet.getRange('A1:B1').format.fill='#FFFFFF';sheet.getRange('A1:B1').format.font={name:'Arial',size:16,bold:true,color:'#233D32'};
    sheet.getRange('A:A').format.columnWidth=30;sheet.getRange('B:B').format.columnWidth=94;
    sheet.getRange('A2:B2').format.fill='#233D32';sheet.getRange('A2:B2').format.font={bold:true,color:'#FFFFFF'};
    sheet.getRange('A3:A20').format.font={bold:true,color:'#253D32'};
    sheet.getRange('B5:B11').setNumberFormat('#,##0');
  }else{
    sheet.freezePanes.freezeRows(1);
    for(let i=1;i<rows.length;i++)if(i%2===0)sheet.getRangeByIndexes(i,0,1,columns).format.fill='#F0F3ED';
    for(let c=0;c<columns;c++){
      const label=input[0][c]||'';
      if(/reference|raw_value|reason|definition|validation|missing_behavior|handling|risk|identity_flags/.test(label))sheet.getRangeByIndexes(0,c,rows.length,1).format.columnWidth=50;
      if(/township|village/.test(label))sheet.getRangeByIndexes(0,c,rows.length,1).format.columnWidth=28;
      if(/population|households|deaths|injuries|missing$|houses_|quantity|stock|gap/.test(label))sheet.getRangeByIndexes(1,c,Math.max(1,rows.length-1),1).setNumberFormat('#,##0');
      if(/(?:_at|timestamp_utc)$/.test(label))sheet.getRangeByIndexes(1,c,Math.max(1,rows.length-1),1).setNumberFormat('yyyy-mm-dd hh:mm:ss');
    }
    if(rows.length>1){const table=sheet.tables.add(sheet.getRangeByIndexes(0,0,rows.length,columns),true,'T'+name.replace(/[^A-Za-z0-9]/g,''));table.style='TableStyleLight1';}
    for(let r=1;r<rows.length;r++){
      const lines=Math.max(1,...rows[r].map((v,c)=>Math.ceil(String(v??'').length/(/reference|raw_value|reason|definition|validation|missing_behavior|handling|risk|identity_flags/.test(input[0][c]||'')?55:30))));
      sheet.getRangeByIndexes(r,0,1,columns).format.rowHeight=Math.min(210,Math.max(40,lines*17+12));
    }
  }
  if(name==='04_Needs')sheet.getRangeByIndexes(1,1,Math.max(1,rows.length-1),columns-2).dataValidation={rule:{type:'list',values:['none','low','medium','high','critical']}};
  if(name==='08_Verification_Queue')sheet.getRangeByIndexes(1,3,Math.max(1,rows.length-1),1).dataValidation={rule:{type:'list',values:['submitted','needs_review','verified','rejected','superseded']}};
  const preview=await workbook.render({sheetName:name,range:name==='00_Read_Me'?'A1:B14':name==='06_Assistance'?'A1:F3':'A1:'+String.fromCharCode(64+Math.min(columns,6))+'8',scale:1.2,format:'png'});
  await fs.writeFile(path.join(output,'qa',name+'.png'),new Uint8Array(await preview.arrayBuffer()));
}
const inspected=await workbook.inspect({kind:'table',range:'00_Read_Me!A1:B14',include:'values',tableMaxRows:14,tableMaxCols:2,maxChars:4000});
console.log(inspected.ndjson);
const errors=await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'Formula error scan'});
console.log(errors.ndjson);
const xlsx=await SpreadsheetFile.exportXlsx(workbook);await xlsx.save(path.join(output,'Flood_Intelligence_Processed.xlsx'));
console.log(JSON.stringify({output:path.join(output,'Flood_Intelligence_Processed.xlsx'),sheets:Object.keys(tabs).length}));
