import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    // Flask 가 정적 파일을 서빙 — 동일 오리진이라 rewrites 불필요
    output: "export",
    trailingSlash: true,
    images: {
        unoptimized: true, // static export 필수
    },
};

export default nextConfig;
