import { Config } from "@remotion/cli/config";

// Quality-first, deterministic output: lossless-ish intermediate frames, high bitrate H.264.
Config.setVideoImageFormat("png");
Config.setCodec("h264");
Config.setCrf(15);
Config.setPixelFormat("yuv420p");
Config.setOverwriteOutput(true);
Config.setPublicDir("public");
