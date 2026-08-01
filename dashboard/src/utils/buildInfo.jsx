const deployVersion = process.env.REACT_APP_DEPLOY_VERSION || "dev";
const deployCommit = process.env.REACT_APP_DEPLOY_COMMIT || "local";

export const buildDisplayVersion = `v${deployVersion}`;
export const buildDisplayCommit = deployCommit;
export const buildDisplayLabel = `${buildDisplayVersion} (${buildDisplayCommit})`;
