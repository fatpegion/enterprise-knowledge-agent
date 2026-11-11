// Optional localhost adapter for reproducing the live evaluation.
import { createServer } from "node:http";
import { getLlama, LlamaChatSession } from "node-llama-cpp";

const [modelPath, port] = process.argv.slice(2);
const llama = await getLlama({ gpu: false, build: "never" });
const model = await llama.loadModel({ modelPath });
const context = await model.createContext({ contextSize: 8192, threads: 6 });
const grammar = await llama.getGrammarFor("json");
const contextSequence = context.getSequence();
let busy = false;

createServer(async (request, response) => {
    response.setHeader("Content-Type", "application/json");
    if (request.url === "/health") {
        response.end(JSON.stringify({ status: "ok" }));
        return;
    }
    if (request.method !== "POST" || request.url !== "/v1/chat/completions") {
        response.statusCode = 404;
        response.end("{}");
        return;
    }
    if (busy) {
        response.statusCode = 503;
        response.end("{}");
        return;
    }

    busy = true;
    let session;
    try {
        const chunks = [];
        for await (const chunk of request) {
            chunks.push(chunk);
        }
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        session = new LlamaChatSession({
            contextSequence,
            systemPrompt: body.messages[0].content,
        });
        const content = await session.prompt(body.messages[1].content, {
            grammar,
            temperature: body.temperature,
            maxTokens: body.max_tokens,
        });
        response.end(JSON.stringify({ choices: [{ message: { content } }] }));
    } catch (error) {
        console.error(error);
        response.statusCode = 500;
        response.end("{}");
    } finally {
        session?.dispose({ disposeSequence: false });
        busy = false;
    }
}).listen(Number(port), "127.0.0.1");
