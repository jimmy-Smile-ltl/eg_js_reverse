// 可选对拍：从 stdin 读取 JSON 数组，调用 SafeLine calc.wasm，输出结果数组。
// 用法: node reference/wasm_check.mjs < cases.json
import fs from "fs";

const wasm = fs.readFileSync(new URL("./calc.wasm", import.meta.url));
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
const { instance } = await WebAssembly.instantiate(wasm, {});
const ex = instance.exports;

const results = [];
for (const data of cases) {
  ex.reset();
  for (const v of data) ex.arg(v);
  const n = ex.calc();
  results.push(Array.from({ length: n }, () => ex.ret()));
}
console.log(JSON.stringify(results));
