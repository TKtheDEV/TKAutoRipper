function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  const wrapper = document.createElement("div");
  wrapper.classList.add("toast-msg");
  if (type === "error") wrapper.style.borderLeft = "5px solid red";
  wrapper.textContent = message;
  toast.appendChild(wrapper);
  
  setTimeout(() => wrapper.classList.add("fade-out"), 3000);
  setTimeout(() => wrapper.remove(), 4000);
}
