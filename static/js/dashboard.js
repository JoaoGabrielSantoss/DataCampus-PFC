(function () {
    const source = document.getElementById("dashboard-data");
    if (!source) return;
    const data = JSON.parse(source.textContent);
    const params = new URLSearchParams(window.location.search);

    function navigate(key, value) {
        const current = params.get(key) || "";
        if (current === String(value)) params.delete(key);
        else params.set(key, value);
        window.location.search = params.toString();
    }

    function node(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }

    const statusRoot = document.getElementById("grafico-situacoes");
    const statusClasses = { elegivel: "barra-elegivel", pendente: "barra-pendente", inelegivel: "barra-inelegivel" };
    if (statusRoot) {
        const all = data.situacoes.reduce((sum, item) => sum + item.total, 0);
        data.situacoes.forEach((item) => {
            const button = node("button", "situacao-linha" + (params.get("situacao") === item.key ? " selecionada" : ""));
            button.type = "button";
            button.setAttribute("aria-label", `${item.label}: ${item.total}. Clique para filtrar`);
            const heading = node("span", "situacao-cabecalho");
            heading.append(node("span", "situacao-nome", item.label), node("strong", "situacao-total", String(item.total)));
            const track = node("span", "situacao-trilho");
            const fill = node("span", statusClasses[item.key] || "barra-pendente");
            fill.style.width = `${all ? (item.total / all) * 100 : 0}%`;
            track.append(fill);
            button.append(heading, track);
            button.addEventListener("click", () => navigate("situacao", item.key));
            statusRoot.append(button);
        });
    }

    const studiesRoot = document.getElementById("grafico-estudos");
    if (studiesRoot) {
        const max = Math.max(1, ...data.estudos.map((item) => item.total));
        data.estudos.forEach((item) => {
            const button = node("button", "estudo-barra" + (params.get("estudo") === String(item.id) ? " selecionada" : ""));
            button.type = "button";
            button.setAttribute("aria-label", `${item.nome}: ${item.total} participações. Clique para filtrar`);
            const label = node("span", "estudo-barra-nome", item.nome);
            const track = node("span", "estudo-barra-trilho");
            const fill = node("span", "estudo-barra-preenchimento");
            fill.style.width = `${(item.total / max) * 100}%`;
            track.append(fill);
            button.append(label, track, node("strong", "estudo-barra-total", String(item.total)));
            button.addEventListener("click", () => navigate("estudo", item.id));
            studiesRoot.append(button);
        });
        if (!data.estudos.length) studiesRoot.append(node("p", "grafico-vazio", "Ainda não há participações para exibir."));
    }

    const svg = document.getElementById("grafico-tendencia");
    if (svg) {
        const ns = "http://www.w3.org/2000/svg";
        const make = (tag, attributes) => {
            const element = document.createElementNS(ns, tag);
            Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
            return element;
        };
        const values = data.meses;
        const width = 720, height = 250, left = 36, right = 14, top = 20, bottom = 42;
        const plotWidth = width - left - right, plotHeight = height - top - bottom;
        const max = Math.max(1, ...values.map((item) => item.total));
        [0, .5, 1].forEach((fraction) => {
            const y = top + plotHeight * fraction;
            svg.append(make("line", { x1: left, y1: y, x2: width - right, y2: y, class: "grafico-grade" }));
            const label = make("text", { x: left - 10, y: y + 4, "text-anchor": "end", class: "grafico-eixo" });
            label.textContent = String(Math.round(max * (1 - fraction)));
            svg.append(label);
        });
        const points = values.map((item, index) => ({
            ...item,
            x: values.length < 2 ? left + plotWidth / 2 : left + (index / (values.length - 1)) * plotWidth,
            y: top + plotHeight - (item.total / max) * plotHeight,
        }));
        if (points.length) {
            const areaPath = `M ${points[0].x} ${top + plotHeight} ` + points.map((point) => `L ${point.x} ${point.y}`).join(" ") + ` L ${points[points.length - 1].x} ${top + plotHeight} Z`;
            svg.append(make("path", { d: areaPath, class: "grafico-area" }));
            svg.append(make("polyline", { points: points.map((point) => `${point.x},${point.y}`).join(" "), class: "grafico-curva" }));
            points.forEach((point, index) => {
                const circle = make("circle", { cx: point.x, cy: point.y, r: 4, class: "grafico-ponto", tabindex: "0" });
                const title = make("title", {});
                title.textContent = `${point.label}: ${point.total} participação(ões)`;
                circle.append(title);
                svg.append(circle);
                if (index === 0 || index === points.length - 1 || index % 3 === 0) {
                    const label = make("text", { x: point.x, y: height - 12, "text-anchor": "middle", class: "grafico-eixo" });
                    label.textContent = point.label;
                    svg.append(label);
                }
            });
        }
    }
})();
