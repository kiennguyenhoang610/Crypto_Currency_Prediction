'use strict';

///////////////////////////////////////
// Modal window

const modal = document.querySelector('.modal');
const overlay = document.querySelector('.overlay');
const btnCloseModal = document.querySelector('.btn--close-modal');
const btnsOpenModal = document.querySelectorAll('.btn--show-modal');
const btnScrollTo = document.querySelector('.btn--scroll-to')
const section1 = document.querySelector('#section--1')
const nav = document.querySelector('.nav')
const tabs = document.querySelectorAll('.operations__tab')
const tabsContainer  = document.querySelector('.operations__tab-container')
const tabsContent    = document.querySelectorAll('.operations__content')
const openModal = function (e) {
  e.preventDefault()
  modal.classList.remove('hidden');
  overlay.classList.remove('hidden');
};

const closeModal = function () {
  modal.classList.add('hidden');
  overlay.classList.add('hidden');
};

btnsOpenModal.forEach(btn => btn.addEventListener ('click', openModal))

for (let i = 0; i < btnsOpenModal.length; i++)
  btnsOpenModal[i].addEventListener('click', openModal);

btnCloseModal.addEventListener('click', closeModal);
overlay.addEventListener('click', closeModal);

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
    closeModal();
  }
});
//Selecting elements
console.log(document.documentElement)
console.log(document.head)
console.log(document.body)

const header = document.querySelector('.header')
// const allSections = document.querySelectorAll('.section')
// console.log(allSections)

document.getElementById('section--1')
const allButtons = document.getElementsByTagName('button')
console.log(allButtons)

// Creating and inserting elements
const message = document.createElement('div')
message.classList.add('cookie-message')
// message.textContent = 'We use cookied for improved functionality and analytics'
message.innerHTML = 
'We use cookied for improved functionality and analytics,<button class="btn btn--close-cookie">Got it!</button>'

header.prepend(message)
header.append(message)

//Delete elements
document
    .querySelector('.btn--close-cookie')
    .addEventListener('click', function () {
      message.parentElement.removeChild(message)
    })

//Styles
message.style.backgroundColor =  '#37383d'
message.style.width           =   '120%'

console.log(message.style.height)
console.log(message.style.backgroundColor)

console.log(getComputedStyle(message).color)



btnScrollTo.addEventListener('click', function(e)
{
  const s1coords = section1.getBoundingClientRect()
  console.log(s1coords)

  console.log(e.target.getBoundingClientRect())

  // console.log('Current scroll (X/Y)', window.pageXOffset, window.pageYOffset)

  console.log('height/width viewport',
              document.documentElement.clientHeight,
              document.documentElement.clientWidth)
                        
    //Scrolling
  // window.scrollTo({
  //     left: s1coords.left + window.pageXOffset, 
  //     top : s1coords.top  + window.pageYOffset,
  //     behavior : 'smooth'})
  section1.scrollIntoView({behavior : "smooth"})
            })

// const h1 =  document.querySelector('h1')
// h1.addEventListener('mouseenter', function(e){
//   alert('addEventlistenner: Great! you are reading the heading :D')
// })

// h1.onmouseenter = function(e){
//   alert('addEventlistenner: Great! you are reading the heading :D')
// }

const randomInt = (min, max) => 
  Math.floor(Math.random() *(max - min +1) +min)
const randomColor = () =>
  `rgb(${randomInt(0, 255)}, ${randomInt(0, 255)}, ${randomInt(0, 255)})  `

document.querySelector('.nav__link').addEventListener
('click', function(e){
})

document.querySelector('.nav__links').addEventListener
('click', function(e){
})

document.querySelector('.nav').addEventListener
('click', function(e) { 
})

///////////////////////////////////////////////////////////////
////////////Page navigation
document
    .querySelectorAll('.nav__link')
    .forEach(
    function(el){
      el.addEventListener('click', function(e){
          e.preventDefault()
          const id  = this.getAttribute('href')
          console.log(id)
          document.querySelector(id).scrollIntoView({behavior : "smooth"})
      })
})

const h1  = document.querySelector('h1')

//Going downward: child?
console.log(h1.querySelectorAll('.highlight'))
console.log(h1.childNodes)
console.log(h1.children)

//Tabbed component 


tabsContainer.addEventListener('click', function (e){
  const clicked  =e.target.closest('.operation__tab')
  //Guard clause 
  if (!clicked ) return

  //Remove active classes
  tabs.forEach(t => t.classList.remove('operations__tab--active'))
  tabsContent.forEach(t => t.classList.remove('operations__content--active'))

  //Active tab
  clicked.classList.add('operations__tab--active')
  //Activate content area
  document
    .querySelector(`.opearaions__content--${clicked.dataset.tab}`)
    .classList.add('opearations__content--active')
})

//Menu fade animation 
const handlerHover  = function (e) {
  if(e.target.classList.contains('nav__link')) {
    const link = e.target
    const siblings = link.closest('.nav').querySelectorAll('.nav__link')
    const logo = link.closest('.nav').querySelector('img')

    siblings.forEach(el => {
      if(el !== link) el.style.opacity  = this
    })
    logo.style.opacity = this

  }
}
nav.addEventListener('mouseover', handlerHover.bind(0.5))
nav.addEventListener('mouseout',handlerHover.bind(1.0))

//Sticky navigation
const intitalCoords = section1.getBoundingClientRect()
console.log(intitalCoords)
window.addEventListener('scroll', function(e){
  console.log(this.window.scrollY)
  if (this.window.scrollY > intitalCoords.top) nav.classList.add('sticky')
  else nav.classList.remove('sticky')
})

//Observer
// 
const header1 = document.querySelector('.header')
// const revealSection = document.querySelectorAll('.section--hidden') 
const stickyNav = function(entries){
  const [entry]  = entries
  console.log(entry)

  if (!entry.isIntersecting) nav.classList.add('sticky')
  else nav.classList.remove('sticky')
}
const headerObserver = new IntersectionObserver
(stickyNav, {
    root: null,
    threshold: 0,
    rootMargin: '-90px'
})

headerObserver.observe(header1)
//Reveal section
const allSections = document.querySelectorAll('.section')
const revealSection  = function (entries, observer){
  const [entry] = entries
  console.log(entry)
  entry.target.classList.remove('section--hidden')
}
const sectionObserver  = new IntersectionObserver
(revealSection, {
  root :null,
  threshold: 0.15
}
)
allSections.forEach(function (section){
  
  sectionObserver.observe(section)
  // section.classList.add('section--hidden')
})
const imgTargets = document.querySelectorAll('img[data-src]')

const loadImg = function (entries, observer){
  const [entry] = entries
  console.log(entry)  
  if(!entry.isIntersecting) return
  // Repalce src with data-src
  entry.target.src = entry.target.dataset.src
 
  entry.target.addEventListener('load', function() {
    entry.target.classList.remove('lazy-img')
  })
  observer.unobserve(entry.target)
}
const imgObserver = new IntersectionObserver(loadImg,
  {
    root: null,
    threshold: 0,
    rootMargin: '200px'
  })
imgTargets.forEach(img => imgObserver.observe(img))

//Silder
let curSlide = 0
const slides = document.querySelectorAll('.slide')  
const btnLeft  = document.querySelector('.slider__btn--left')
const btnRight  = document.querySelector('.slider__btn--right')
const maxSlide =  slides.length
const dotContainer  = document.querySelector('.dots') 
// const slider = document.querySelector('.slider')
// slider.style.transform = 'scale(0.5) translatex(-800px)'
// slider.style.overflow  = 'visable'

slides.forEach((s, i) =>  s.style.transform = `translateX(${100*i}%)`)


const createDots  = function (){
  slides.forEach(function(_, i){
    dotContainer.insertAdjacentHTML('beforeend',
    ` <button class="dots__dot" data-slide="${i}"></button>`)
  })
}
createDots()

const activateDot = function(slide){
  document
        .querySelectorAll('.dots__dot')
        .forEach(dot => dot.classList.remove('dots__dot--active'))

  document.querySelector(`.dots__dot[data-slide="${slide}"]`)
          .classList.add('dots__dot--active')
}
activateDot(0)
document.addEventListener('keydown', function(e){
  console.log(e)
  if(e.key === 'ArrowLeft') prvslide()
  e.key === 'ArrowRight' && nextslide()
})

dotContainer.addEventListener('click', function(e){
  if(e.target.classList.contains('dots__dot')){
    const {slide} = e.target.dataset
    gotoSlide(slide)
    activateDot(slide)
  }
})

//Next slide
const gotoSlide = function(slide){
  slides.forEach((s, i) =>  s.style.transform = `translateX(${100*(i - slide)}%)`)
}
gotoSlide(0)  
const nextslide = function(){
  if (curSlide === maxSlide -1){
    curSlide = 0
  
  }else {
    curSlide++
  }
  gotoSlide(curSlide)
  activateDot(curSlide)

}
const prvslide = function(){
  curSlide--  
  gotoSlide(curSlide)
  activateDot(prvslide)

}
// Data crawling
console.log(tabsContainer)
// tabsContainer.addEventListener('')
btnLeft.addEventListener('click', prvslide)
btnRight.addEventListener('click', nextslide)

document.addEventListener('DOMContentLoaded',
function(e){
  console.log('HTML parsed and DOM tree built', e)
})

window.addEventListener('load', function(e){
  console.log('Page fully load!',e )
})

window.addEventListener('beforeunload', function(e){
  e.preventDefault()
  console.log(e)
  e.returnValue = 'message'
})
