// API Service Module: Handles all backend API communication
const ApiService = {
  async getProjects() {
    const res = await fetch("/api/projects");
    return await res.json();
  },

  async createProject(name, baseUrl = "") {
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, base_url: baseUrl })
    });
    return await res.json();
  },

  async updateProject(id, data) {
    const res = await fetch(`/api/projects/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return await res.json();
  },

  async deleteProject(id) {
    const res = await fetch(`/api/projects/${id}`, { method: "DELETE" });
    return await res.json();
  },

  async getProjectRequests(projectId) {
    const res = await fetch(`/api/projects/${projectId}/requests`);
    return await res.json();
  },

  async createRequest(projectId, data) {
    const res = await fetch(`/api/projects/${projectId}/requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return await res.json();
  },

  async getRequest(id) {
    const res = await fetch(`/api/requests/${id}`);
    return await res.json();
  },

  async updateRequest(id, data) {
    const res = await fetch(`/api/requests/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return await res.json();
  },

  async deleteRequest(id) {
    const res = await fetch(`/api/requests/${id}`, { method: "DELETE" });
    return await res.json();
  },

  async executeRequest(payload) {
    const res = await fetch("/api/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return await res.json();
  },

  async importCollection(data) {
    const res = await fetch("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return await res.json();
  }
};
