function toggleTheme() {
    const body = document.body;
    const header = document.querySelector('header');
    const footer = document.querySelector('footer');
    const nav = document.querySelector('nav');
    body.classList.toggle('dark-mode');
    header.classList.toggle('dark-mode');
    footer.classList.toggle('dark-mode');
    nav.classList.toggle('dark-mode');
}
