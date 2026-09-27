FROM node:20-slim

WORKDIR /app

# The lockfile is copied and npm ci is used deliberately.
#
# This previously copied package.json alone and ran `npm install`, which
# ignores package-lock.json and re-resolves every dependency inside its
# semver range on every build. The same commit therefore produced a
# different node_modules depending on the day it was built — and one such
# rebuild installed a vite/rolldown combination whose own config loader
# crashed at startup:
#
#   failed to load config from /app/vite.config.js
#   TypeError: The "paths[1]" argument must be of type string.
#       at sourcemapPathTransform (vite/dist/node/chunks/node.js)
#
# with nothing in this repository having changed to cause it. npm ci installs
# exactly what the lockfile pins, so a build is reproducible and Dependabot's
# lockfile updates are what actually reach the image.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]
