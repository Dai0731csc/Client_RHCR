(function initSharedBasePath(global) {
  function createWithBasePath(basePath) {
    return function withBasePath(path) {
      if (!path) {
        return basePath || "";
      }
      if (!path.startsWith("/")) {
        path = `/${path}`;
      }
      return basePath ? `${basePath}${path}` : path;
    };
  }

  global.SharedBasePath = {
    createWithBasePath,
  };
})(window);
